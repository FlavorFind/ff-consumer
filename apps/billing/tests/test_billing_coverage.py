"""Billing coverage gap tests — seed_plans command, subscribe edge cases,
Paystack initialize with real API mock, webhook exception handling, _get_client_ip.

Targets 95%+ coverage for apps/billing.
"""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

# ---------------------------------------------------------------------------
# seed_plans management command
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSeedPlansCommand:
    def test_seed_creates_plans(self, db):
        from apps.billing.models import Plan

        # Ensure clean slate
        Plan.objects.all().delete()

        out = StringIO()
        call_command("seed_plans", stdout=out)
        output = out.getvalue()

        assert "Created plan: free" in output
        assert "Created plan: plus" in output
        assert "Created: 2" in output
        assert Plan.objects.count() == 2

    def test_seed_skips_existing(self, db):
        from apps.billing.models import Plan

        Plan.objects.all().delete()
        call_command("seed_plans")  # first run creates

        out = StringIO()
        call_command("seed_plans", stdout=out)
        output = out.getvalue()

        assert "Skipped (already exists): free" in output
        assert "Skipped (already exists): plus" in output
        assert "Skipped: 2" in output

    def test_seed_update_mode_updates_existing(self, db):
        from apps.billing.models import Plan

        Plan.objects.all().delete()
        Plan.objects.create(code="plus", name="Old Name", price_kes="99.00", features=["old"])

        out = StringIO()
        call_command("seed_plans", "--update", stdout=out)
        output = out.getvalue()

        plan = Plan.objects.get(code="plus")
        assert plan.name == "Flavor Find Plus"
        assert str(plan.price_kes) == "199.00"
        assert "meal_plans" in plan.features
        assert "Updated" in output


# ---------------------------------------------------------------------------
# Subscribe edge cases
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSubscribeEdgeCases:
    def test_subscribe_plan_not_in_db_returns_404(self, db):
        """Subscribe to 'plus' when no Plus plan exists in DB → 404."""
        from apps.billing.models import Plan

        Plan.objects.all().delete()

        User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()
        u = User.objects.create_user(
            email="subtest@example.com", username="subtest", password="pass123"
        )
        client = APIClient()
        refresh = RefreshToken.for_user(u)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = client.post("/v1/subscribe/", {"plan_code": "plus"}, format="json")
        assert response.status_code == 404
        assert "not_found" in response.json()["error"]["code"]

    def test_subscribe_updates_existing_subscription_plan(self, db):
        """User with existing free subscription switches to plus."""
        from apps.billing.models import Plan, Subscription

        free = Plan.objects.create(code="free", name="Free", price_kes="0.00", features=[])
        Plan.objects.create(code="plus", name="Plus", price_kes="199.00", features=[])

        User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()
        u = User.objects.create_user(
            email="switch@example.com", username="switch", password="pass123"
        )
        # User already has a free subscription
        sub = Subscription.objects.create(user=u, plan=free, status=Subscription.Status.ACTIVE)

        client = APIClient()
        refresh = RefreshToken.for_user(u)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = client.post("/v1/subscribe/", {"plan_code": "plus"}, format="json")
        assert response.status_code == 200

        sub.refresh_from_db()
        assert sub.plan_id == "plus"


# ---------------------------------------------------------------------------
# Paystack initialize with real API mock
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPaystackInitialize:
    def test_initialize_with_api_key_calls_paystack(self, db):
        """When PAYSTACK_SECRET_KEY is set, _initialize_paystack_transaction calls the API."""
        from apps.billing.views import _initialize_paystack_transaction

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": True,
            "data": {
                "authorization_url": "https://checkout.paystack.com/test123",
                "access_code": "access_test",
                "reference": "ref-123",
            },
        }

        with (
            override_settings(PAYSTACK_SECRET_KEY="sk_test_123"),
            patch("requests.post") as mock_post,
        ):
            mock_post.return_value = mock_response
            result = _initialize_paystack_transaction(
                email="test@example.com",
                amount_kes=199,
                reference="ref-123",
                metadata={"key": "value"},
            )

            assert result["authorization_url"] == "https://checkout.paystack.com/test123"
            assert mock_post.call_count == 1
            # Verify the request payload
            call_args = mock_post.call_args
            assert call_args.kwargs["json"]["email"] == "test@example.com"
            assert call_args.kwargs["json"]["amount"] == 19900
            assert call_args.kwargs["json"]["currency"] == "KES"
            assert call_args.kwargs["headers"]["Authorization"] == "Bearer sk_test_123"

    def test_initialize_paystack_error_raises(self, db):
        """Paystack API error is logged and re-raised."""
        from apps.billing.views import _initialize_paystack_transaction

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": False,
            "message": "Invalid key",
        }

        with (
            override_settings(PAYSTACK_SECRET_KEY="sk_test_bad"),
            patch("requests.post") as mock_post,
        ):
            mock_post.return_value = mock_response
            with pytest.raises(ValueError, match="Paystack error"):
                _initialize_paystack_transaction(
                    email="test@example.com",
                    amount_kes=199,
                    reference="ref-err",
                )

    def test_initialize_network_error_raises(self, db):
        """Network error during Paystack call is logged and re-raised."""
        from apps.billing.views import _initialize_paystack_transaction

        with (
            override_settings(PAYSTACK_SECRET_KEY="sk_test_net"),
            patch("requests.post") as mock_post,
        ):
            mock_post.side_effect = ConnectionError("Network down")
            with pytest.raises(ConnectionError):
                _initialize_paystack_transaction(
                    email="test@example.com",
                    amount_kes=199,
                    reference="ref-net",
                )


# ---------------------------------------------------------------------------
# Webhook exception handling
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebhookExceptionHandling:
    def test_webhook_catches_unexpected_exception(self, api_client):
        """Webhook returns 200 even if internal processing throws."""
        import hashlib
        import hmac

        body = json.dumps({"event": "charge.success", "data": {"reference": "x"}}).encode()
        sig = hmac.new(b"test_key", body, hashlib.sha512).hexdigest()

        with (
            override_settings(PAYSTACK_SECRET_KEY="test_key"),
            patch(
                "apps.billing.views.PaystackWebhookView._process_event",
                side_effect=RuntimeError("Unexpected crash"),
            ),
        ):
            response = api_client.post(
                "/v1/paystack/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# _get_client_ip helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetClientIp:
    def test_x_forwarded_for(self):
        from apps.billing.views import _get_client_ip

        class MockRequest:
            META = {"HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8", "REMOTE_ADDR": "127.0.0.1"}

        assert _get_client_ip(MockRequest()) == "1.2.3.4"

    def test_remote_addr_fallback(self):
        from apps.billing.views import _get_client_ip

        class MockRequest:
            META = {"REMOTE_ADDR": "192.168.1.1"}

        assert _get_client_ip(MockRequest()) == "192.168.1.1"

    def test_empty_forwarded_for_falls_back_to_remote_addr(self):
        from apps.billing.views import _get_client_ip

        class MockRequest:
            META = {"HTTP_X_FORWARDED_FOR": "", "REMOTE_ADDR": "10.0.0.1"}

        # Empty string is falsy, so it falls back
        assert _get_client_ip(MockRequest()) == "10.0.0.1"
