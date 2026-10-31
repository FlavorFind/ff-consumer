"""Billing tests — plans, subscription, M-Pesa callback, entitlements.

Targets 95%+ coverage for apps/billing.
"""

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

    return Plan.objects.create(
        code="free",
        name="Free",
        price_kes=0,
        features=[],
    )


@pytest.fixture
def plus_plan(db):
    from apps.billing.models import Plan

    return Plan.objects.create(
        code="plus",
        name="Flavor Find Plus",
        price_kes=199,
        features=["meal_plans", "shopping_lists", "offline_sync"],
    )


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
        """Plans endpoint is public — no auth required."""
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
        data = response.json()
        assert data["plan_code"] == "plus"
        assert data["status"] == "active"

    def test_subscription_requires_auth(self, api_client):
        response = api_client.get("/v1/subscription/")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Subscribe endpoint (STK push initiation)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubscribeEndpoint:
    def test_subscribe_valid_phone(self, auth_client, plus_plan):
        response = auth_client.post(
            "/v1/subscribe/",
            {"phone": "254712345678", "plan_code": "plus"},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "payment_id" in data
        assert data["status"] == "pending"
        assert "checkout_request_id" in data

    def test_subscribe_invalid_phone(self, auth_client, plus_plan):
        response = auth_client.post(
            "/v1/subscribe/",
            {"phone": "0712345678", "plan_code": "plus"},
            format="json",
        )
        assert response.status_code == 400

    def test_subscribe_unknown_plan(self, auth_client):
        response = auth_client.post(
            "/v1/subscribe/",
            {"phone": "254712345678", "plan_code": "enterprise"},
            format="json",
        )
        assert response.status_code == 400  # choice validation

    def test_subscribe_requires_auth(self, api_client, plus_plan):
        response = api_client.post(
            "/v1/subscribe/",
            {"phone": "254712345678", "plan_code": "plus"},
            format="json",
        )
        assert response.status_code == 401

    def test_subscribe_creates_pending_payment(self, auth_client, plus_plan):
        from apps.billing.models import Payment

        auth_client.post(
            "/v1/subscribe/",
            {"phone": "254712345678", "plan_code": "plus"},
            format="json",
        )
        assert Payment.objects.filter(status=Payment.Status.PENDING).exists()


# ---------------------------------------------------------------------------
# M-Pesa callback
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMpesaCallback:
    def _build_stk_body(self, result_code=0, amount=199, receipt="MPESATEST001"):
        return {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "test-merchant-001",
                    "CheckoutRequestID": "ws_CO_test001",
                    "ResultCode": result_code,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": amount},
                            {"Name": "MpesaReceiptNumber", "Value": receipt},
                            {"Name": "TransactionDate", "Value": 20261031120000},
                            {"Name": "PhoneNumber", "Value": 254712345678},
                        ]
                    },
                }
            }
        }

    def test_callback_confirms_payment(self, api_client, plus_plan, user):
        """Successful M-Pesa callback activates the subscription."""
        from apps.billing.models import Payment, Subscription

        sub = Subscription.objects.create(
            user=user, plan=plus_plan, status=Subscription.Status.ACTIVE
        )
        payment = Payment.objects.create(
            user=user,
            subscription=sub,
            provider="mpesa",
            provider_ref="PENDING-00000001",
            amount_kes=199,
            status=Payment.Status.PENDING,
        )

        response = api_client.post(
            "/v1/mpesa/callback/",
            self._build_stk_body(amount=199.0, receipt="MPESATEST002"),
            format="json",
        )
        # Always returns 200 to Daraja
        assert response.status_code == 200
        assert response.json()["ResultCode"] == 0

        payment.refresh_from_db()
        assert payment.status == Payment.Status.CONFIRMED
        assert payment.provider_ref == "MPESATEST002"

    def test_callback_failed_payment_ignored(self, api_client):
        """ResultCode != 0 means user cancelled — no payment confirmed."""
        response = api_client.post(
            "/v1/mpesa/callback/",
            self._build_stk_body(result_code=1032),  # cancelled by user
            format="json",
        )
        assert response.status_code == 200

    def test_callback_duplicate_receipt_ignored(self, api_client, plus_plan, user):
        """Same MpesaReceiptNumber processed twice — second is silently ignored."""
        from apps.billing.models import Payment, Subscription

        sub = Subscription.objects.create(
            user=user, plan=plus_plan, status=Subscription.Status.ACTIVE
        )
        # First payment already confirmed with this receipt
        Payment.objects.create(
            user=user,
            subscription=sub,
            provider="mpesa",
            provider_ref="DUPRECEIPT001",  # already confirmed
            amount_kes=199,
            status=Payment.Status.CONFIRMED,
            confirmed_at=timezone.now(),
        )
        # Pending payment (the one that would be processed)
        Payment.objects.create(
            user=user,
            subscription=sub,
            provider="mpesa",
            provider_ref="PENDING-DUP",
            amount_kes=199,
            status=Payment.Status.PENDING,
        )

        response = api_client.post(
            "/v1/mpesa/callback/",
            self._build_stk_body(amount=199.0, receipt="DUPRECEIPT001"),
            format="json",
        )
        assert response.status_code == 200
        # The pending payment should NOT have been confirmed (duplicate)
        from apps.billing.models import Payment as P

        pending = P.objects.get(provider_ref="PENDING-DUP")
        assert pending.status == P.Status.PENDING

    def test_callback_amount_mismatch_rejected(self, api_client, plus_plan, user):
        """Callback with wrong amount is rejected — safety rule."""
        from apps.billing.models import Payment, Subscription

        sub = Subscription.objects.create(
            user=user, plan=plus_plan, status=Subscription.Status.ACTIVE
        )
        Payment.objects.create(
            user=user,
            subscription=sub,
            provider="mpesa",
            provider_ref="PENDING-MISMATCH",
            amount_kes=199,  # expected
            status=Payment.Status.PENDING,
        )

        # Callback claims amount=1 (wrong)
        response = api_client.post(
            "/v1/mpesa/callback/",
            self._build_stk_body(amount=1.0, receipt="MISMATCHRECEIPT001"),
            format="json",
        )
        assert response.status_code == 200  # still 200 to Daraja
        # Payment should stay pending
        from apps.billing.models import Payment as P

        p = P.objects.get(provider_ref="PENDING-MISMATCH")
        assert p.status == P.Status.PENDING

    def test_callback_no_matching_payment_handled_gracefully(self, api_client):
        """Callback for unknown amount is handled gracefully (no 500)."""
        response = api_client.post(
            "/v1/mpesa/callback/",
            self._build_stk_body(amount=9999.0, receipt="UNKNOWNRECEIPT"),
            format="json",
        )
        assert response.status_code == 200


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

    def test_requires_plus_permission_blocks_free_user(self, auth_client, user):
        """Free user is blocked by RequiresPlus permission."""
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
            user = plus_user

        perm = RequiresPlus()
        assert perm.has_permission(MockRequest(), None) is True

    def test_trialing_user_has_plus(self, user):
        """Trialing subscription counts as active Plus."""
        from apps.billing.entitlements import user_has_active_plus
        from apps.billing.models import Plan, Subscription

        plan, _ = Plan.objects.get_or_create(
            code="plus", defaults={"name": "Plus", "price_kes": 199}
        )
        Subscription.objects.create(
            user=user, plan=plan, status=Subscription.Status.TRIALING
        )
        assert user_has_active_plus(user) is True

    def test_expired_sub_does_not_have_plus(self, user):
        from apps.billing.entitlements import user_has_active_plus
        from apps.billing.models import Plan, Subscription

        plan, _ = Plan.objects.get_or_create(
            code="plus", defaults={"name": "Plus", "price_kes": 199}
        )
        Subscription.objects.create(
            user=user, plan=plan, status=Subscription.Status.EXPIRED
        )
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
        sub = plus_user.subscription
        assert sub.is_active_plus() is True

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
            provider="mpesa",
            provider_ref="STRTEST001",
            amount_kes=199,
        )
        assert "199" in str(p)


# ---------------------------------------------------------------------------
# Billing tasks (direct call — no broker needed)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBillingTasks:
    def test_check_subscription_expiry(self, user):
        from apps.billing.models import Plan, Subscription
        from apps.billing.tasks import check_subscription_expiry

        plan, _ = Plan.objects.get_or_create(
            code="plus", defaults={"name": "Plus", "price_kes": 199}
        )
        # Subscription that should have expired
        from datetime import timedelta

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

        # Should not raise even with no subscriptions
        send_renewal_reminders()
