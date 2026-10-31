"""Billing tests — plans, subscription, Paystack webhook, entitlements.

Targets 95%+ coverage for apps/billing.
"""

import hashlib
import hmac
import json

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def free_plan(db):
    from apps.billing.models import Plan

    return Plan.objects.create(code="free", name="Free", price_kes=0, features=[])


@pytest.fixture
def plus_plan(db):
    from apps.billing.models import Plan

    return Plan.objects.get_or_create(
        code="plus",
        defaults={"name": "Flavor Find Plus", "price_kes": 199, "features": ["meal_plans"]},
    )[0]


@pytest.fixture
def plus_user(db):
    """A user with an active Plus subscription."""
    from django.contrib.auth import get_user_model

    from apps.billing.models import Plan, Subscription

    User = get_user_model()
    u = User.objects.create_user(email="plus@example.com", password="testpass123")
    plan, _ = Plan.objects.get_or_create(
        code="plus",
        defaults={"name": "Plus", "price_kes": 199, "features": []},
    )
    Subscription.objects.create(user=u, plan=plan, status=Subscription.Status.ACTIVE)
    return u


@pytest.fixture
def plus_client(plus_user):
    client = APIClient()
    refresh = RefreshToken.for_user(plus_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


def _paystack_signature(body: bytes, secret: str = "test_secret") -> str:
    """Build a valid Paystack HMAC-SHA512 signature for testing."""
    return hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()


def _webhook_body(reference: str, amount_kobo: int = 19900, event="charge.success") -> bytes:
    payload = {
        "event": event,
        "data": {
            "id": 12345678,
            "reference": reference,
            "amount": amount_kobo,
            "currency": "KES",
            "status": "success",
            "gateway_response": "Successful",
        },
    }
    return json.dumps(payload).encode()


# ---------------------------------------------------------------------------
# Plans endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPlansEndpoint:
    def test_plans_returns_all(self, api_client, free_plan, plus_plan):
        response = api_client.get("/v1/plans/")
        assert response.status_code == 200
        codes = [p["code"] for p in response.json()]
        assert "free" in codes
        assert "plus" in codes

    def test_plans_public_no_auth(self, api_client, free_plan):
        response = api_client.get("/v1/plans/")
        assert response.status_code == 200

    def test_plan_has_required_fields(self, api_client, plus_plan):
        response = api_client.get("/v1/plans/")
        assert response.status_code == 200
        plan = next(p for p in response.json() if p["code"] == "plus")
        assert plan["name"] == "Flavor Find Plus"
        assert plan["price_kes"] == "199.00"
        assert isinstance(plan["features"], list)


# ---------------------------------------------------------------------------
# Subscription endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubscriptionEndpoint:
    def test_subscription_no_record_returns_free(self, auth_client):
        response = auth_client.get("/v1/subscription/")
        assert response.status_code == 200
        data = response.json()
        assert data["plan_code"] == "free"
        assert data["status"] == "active"

    def test_subscription_with_plus_record(self, plus_client):
        response = plus_client.get("/v1/subscription/")
        assert response.status_code == 200
        assert response.json()["plan_code"] == "plus"

    def test_subscription_requires_auth(self, api_client):
        response = api_client.get("/v1/subscription/")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Subscribe endpoint (Paystack initialize)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubscribeEndpoint:
    def test_subscribe_returns_authorization_url(self, auth_client, plus_plan):
        """Subscribe returns a Paystack authorization_url (mocked when no key set)."""
        response = auth_client.post(
            "/v1/subscribe/",
            {"plan_code": "plus"},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "payment_id" in data
        assert "authorization_url" in data
        assert "reference" in data
        assert data["status"] == "pending"

    def test_subscribe_reference_equals_payment_id(self, auth_client, plus_plan):
        """The Paystack reference is the payment UUID — idempotency anchor."""
        response = auth_client.post("/v1/subscribe/", {"plan_code": "plus"}, format="json")
        assert response.status_code == 200
        data = response.json()
        assert data["reference"] == data["payment_id"]

    def test_subscribe_unknown_plan_rejected(self, auth_client):
        response = auth_client.post("/v1/subscribe/", {"plan_code": "enterprise"}, format="json")
        assert response.status_code == 400  # choice validation

    def test_subscribe_requires_auth(self, api_client, plus_plan):
        response = api_client.post("/v1/subscribe/", {"plan_code": "plus"}, format="json")
        assert response.status_code == 401

    def test_subscribe_creates_pending_payment(self, auth_client, plus_plan):
        from apps.billing.models import Payment

        auth_client.post("/v1/subscribe/", {"plan_code": "plus"}, format="json")
        assert Payment.objects.filter(status=Payment.Status.PENDING, provider="paystack").exists()


# ---------------------------------------------------------------------------
# Paystack webhook
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPaystackWebhook:
    def test_webhook_confirms_payment(self, api_client, plus_plan, user):
        """Successful charge.success event activates the subscription."""
        from django.test import override_settings

        from apps.billing.models import Payment, Subscription

        sub = Subscription.objects.create(
            user=user, plan=plus_plan, status=Subscription.Status.ACTIVE
        )
        payment = Payment.objects.create(
            user=user,
            subscription=sub,
            provider="paystack",
            provider_ref="pay-uuid-001",
            amount_kes=199,
            status=Payment.Status.PENDING,
        )

        body = _webhook_body(reference="pay-uuid-001", amount_kobo=19900)
        sig = _paystack_signature(body, secret="test_secret_key")

        with override_settings(PAYSTACK_SECRET_KEY="test_secret_key"):
            response = api_client.post(
                "/v1/paystack/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )

        assert response.status_code == 200
        payment.refresh_from_db()
        assert payment.status == Payment.Status.CONFIRMED
        assert payment.receipt_no == "12345678"

    def test_webhook_invalid_signature_ignored(self, api_client, plus_plan, user):
        """Webhook with invalid signature is ignored — no payment confirmed."""
        from django.test import override_settings

        from apps.billing.models import Payment, Subscription

        sub = Subscription.objects.create(
            user=user, plan=plus_plan, status=Subscription.Status.ACTIVE
        )
        payment = Payment.objects.create(
            user=user,
            subscription=sub,
            provider="paystack",
            provider_ref="pay-uuid-002",
            amount_kes=199,
            status=Payment.Status.PENDING,
        )

        body = _webhook_body(reference="pay-uuid-002", amount_kobo=19900)

        with override_settings(PAYSTACK_SECRET_KEY="test_secret_key"):
            response = api_client.post(
                "/v1/paystack/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE="invalidsignature",
            )

        assert response.status_code == 200  # still 200 to Paystack
        payment.refresh_from_db()
        assert payment.status == Payment.Status.PENDING  # not confirmed

    def test_webhook_duplicate_event_ignored(self, api_client, plus_plan, user):
        """Duplicate charge.success event (same reference) is idempotent."""
        from django.test import override_settings

        from apps.billing.models import Payment, Subscription

        sub = Subscription.objects.create(
            user=user, plan=plus_plan, status=Subscription.Status.ACTIVE
        )
        payment = Payment.objects.create(
            user=user,
            subscription=sub,
            provider="paystack",
            provider_ref="pay-uuid-003",
            amount_kes=199,
            status=Payment.Status.CONFIRMED,  # already confirmed
            confirmed_at=timezone.now(),
        )

        body = _webhook_body(reference="pay-uuid-003", amount_kobo=19900)
        sig = _paystack_signature(body, "test_secret_key")

        with override_settings(PAYSTACK_SECRET_KEY="test_secret_key"):
            api_client.post(
                "/v1/paystack/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )

        # Confirmed_at should not have changed
        payment.refresh_from_db()
        assert payment.status == Payment.Status.CONFIRMED

    def test_webhook_amount_mismatch_rejected(self, api_client, plus_plan, user):
        """Webhook with wrong amount does not confirm the payment — safety rule."""
        from django.test import override_settings

        from apps.billing.models import Payment, Subscription

        sub = Subscription.objects.create(
            user=user, plan=plus_plan, status=Subscription.Status.ACTIVE
        )
        payment = Payment.objects.create(
            user=user,
            subscription=sub,
            provider="paystack",
            provider_ref="pay-uuid-004",
            amount_kes=199,
            status=Payment.Status.PENDING,
        )

        # Webhook claims only KES 1 was paid (100 kobo)
        body = _webhook_body(reference="pay-uuid-004", amount_kobo=100)
        sig = _paystack_signature(body, "test_secret_key")

        with override_settings(PAYSTACK_SECRET_KEY="test_secret_key"):
            response = api_client.post(
                "/v1/paystack/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )

        assert response.status_code == 200
        payment.refresh_from_db()
        assert payment.status == Payment.Status.PENDING  # not confirmed

    def test_webhook_unknown_reference_handled_gracefully(self, api_client):
        """Webhook for unknown reference doesn't crash."""
        from django.test import override_settings

        body = _webhook_body(reference="nonexistent-ref", amount_kobo=19900)
        sig = _paystack_signature(body, "test_secret_key")

        with override_settings(PAYSTACK_SECRET_KEY="test_secret_key"):
            response = api_client.post(
                "/v1/paystack/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )
        assert response.status_code == 200

    def test_webhook_non_charge_event_ignored(self, api_client):
        """Non-charge.success events are silently ignored."""
        from django.test import override_settings

        body = _webhook_body(reference="pay-uuid-005", amount_kobo=19900, event="transfer.success")
        sig = _paystack_signature(body, "test_secret_key")

        with override_settings(PAYSTACK_SECRET_KEY="test_secret_key"):
            response = api_client.post(
                "/v1/paystack/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )
        assert response.status_code == 200

    def test_webhook_no_secret_key_rejects_all(self, api_client):
        """If PAYSTACK_SECRET_KEY is not configured, all webhooks are rejected."""
        from django.test import override_settings

        body = _webhook_body(reference="pay-uuid-006")
        with override_settings(PAYSTACK_SECRET_KEY=""):
            response = api_client.post(
                "/v1/paystack/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE="anything",
            )
        assert response.status_code == 200  # still 200 but nothing processed


# ---------------------------------------------------------------------------
# Entitlements
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEntitlements:
    def test_user_has_active_plus_true(self, plus_user):
        from apps.billing.entitlements import user_has_active_plus

        assert user_has_active_plus(plus_user) is True

    def test_user_has_active_plus_false_for_free_user(self, user):
        from apps.billing.entitlements import user_has_active_plus

        assert user_has_active_plus(user) is False

    def test_user_has_active_plus_false_for_anon(self):
        from apps.billing.entitlements import user_has_active_plus

        assert user_has_active_plus(None) is False

    def test_requires_plus_permission_blocks_free_user(self, user):
        from apps.billing.entitlements import RequiresPlus

        class MockRequest:
            pass

        req = MockRequest()
        req.user = user
        perm = RequiresPlus()
        assert perm.has_permission(req, None) is False

    def test_requires_plus_permission_allows_plus_user(self, plus_user):
        from apps.billing.entitlements import RequiresPlus

        class MockRequest:
            pass

        req = MockRequest()
        req.user = plus_user
        perm = RequiresPlus()
        assert perm.has_permission(req, None) is True

    def test_trialing_user_has_plus(self, user):
        from apps.billing.entitlements import user_has_active_plus
        from apps.billing.models import Plan, Subscription

        plan, _ = Plan.objects.get_or_create(
            code="plus", defaults={"name": "Plus", "price_kes": 199}
        )
        Subscription.objects.create(user=user, plan=plan, status=Subscription.Status.TRIALING)
        assert user_has_active_plus(user) is True

    def test_expired_sub_does_not_have_plus(self, user):
        from apps.billing.entitlements import user_has_active_plus
        from apps.billing.models import Plan, Subscription

        plan, _ = Plan.objects.get_or_create(
            code="plus", defaults={"name": "Plus", "price_kes": 199}
        )
        Subscription.objects.create(user=user, plan=plan, status=Subscription.Status.EXPIRED)
        assert user_has_active_plus(user) is False


# ---------------------------------------------------------------------------
# Billing models
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBillingModels:
    def test_plan_str(self, plus_plan):
        assert "Plus" in str(plus_plan)
        assert "199" in str(plus_plan)

    def test_subscription_str(self, plus_user):
        sub = plus_user.subscription
        assert "plus" in str(sub)

    def test_is_active_plus_method(self, plus_user):
        assert plus_user.subscription.is_active_plus() is True

    def test_is_active_plus_false_for_cancelled(self, plus_user):
        from apps.billing.models import Subscription

        sub = plus_user.subscription
        sub.status = Subscription.Status.CANCELLED
        sub.save()
        assert sub.is_active_plus() is False

    def test_payment_str(self, plus_user):
        from apps.billing.models import Payment

        p = Payment.objects.create(
            user=plus_user,
            subscription=plus_user.subscription,
            provider="paystack",
            provider_ref="str-test-ref-001",
            amount_kes=199,
        )
        assert "199" in str(p)


# ---------------------------------------------------------------------------
# Billing tasks (direct call — no broker needed)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBillingTasks:
    def test_check_subscription_expiry(self, user):
        from datetime import timedelta

        from apps.billing.models import Plan, Subscription
        from apps.billing.tasks import check_subscription_expiry

        plan, _ = Plan.objects.get_or_create(
            code="plus", defaults={"name": "Plus", "price_kes": 199}
        )
        sub = Subscription.objects.create(
            user=user,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            renews_at=timezone.now() - timedelta(days=1),
        )
        check_subscription_expiry()
        sub.refresh_from_db()
        assert sub.status == Subscription.Status.EXPIRED

    def test_check_trial_expiry(self, user):
        from datetime import timedelta

        from apps.billing.models import Plan, Subscription
        from apps.billing.tasks import check_trial_expiry

        plan, _ = Plan.objects.get_or_create(
            code="plus", defaults={"name": "Plus", "price_kes": 199}
        )
        sub = Subscription.objects.create(
            user=user,
            plan=plan,
            status=Subscription.Status.TRIALING,
            trial_ends_at=timezone.now() - timedelta(days=1),
        )
        check_trial_expiry()
        sub.refresh_from_db()
        assert sub.status == Subscription.Status.EXPIRED

    def test_send_renewal_reminders_runs_without_error(self):
        from apps.billing.tasks import send_renewal_reminders

        send_renewal_reminders()
