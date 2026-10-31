"""Billing views — plans, Paystack checkout, subscription status.

Payment flow:
  POST /v1/subscribe/
    → backend calls Paystack Initialize Transaction API
    → returns authorization_url to client
    → user completes payment on Paystack hosted page
    → Paystack POSTs to /v1/paystack/webhook/

Webhook verification:
  - Paystack signs the request body with HMAC-SHA512 using PAYSTACK_SECRET_KEY
  - We verify the X-Paystack-Signature header before processing
  - Amount is re-verified server-side against expected plan price
  - Idempotency: reference is the payment.id UUID (set at initialize time)
"""

import hashlib
import hmac
import logging

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Payment, Plan, Subscription
from apps.core.models import log_audit_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["code", "name", "price_kes", "features"]


class SubscriptionSerializer(serializers.Serializer):
    plan_code = serializers.CharField(source="plan.code")
    plan_name = serializers.CharField(source="plan.name")
    status = serializers.CharField()
    trial_ends_at = serializers.DateTimeField(allow_null=True)
    renews_at = serializers.DateTimeField(allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True)


class SubscribeSerializer(serializers.Serializer):
    """Input for POST /v1/subscribe/."""

    plan_code = serializers.ChoiceField(choices=["plus"], default="plus")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class PlanListView(APIView):
    """GET /v1/plans/ — list available billing plans."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: PlanSerializer(many=True)},
        summary="List billing plans",
        description="Returns Free and Plus plan details.",
    )
    def get(self, request):
        plans = Plan.objects.all().order_by("price_kes")
        return Response(PlanSerializer(plans, many=True).data)


class SubscriptionView(APIView):
    """GET /v1/subscription/ — current user's subscription status."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: SubscriptionSerializer},
        summary="Get subscription status",
    )
    def get(self, request):
        try:
            sub = request.user.subscription
        except Subscription.DoesNotExist:
            return Response(
                {
                    "plan_code": "free",
                    "plan_name": "Free",
                    "status": "active",
                    "trial_ends_at": None,
                    "renews_at": None,
                    "cancelled_at": None,
                }
            )
        return Response(SubscriptionSerializer(sub).data)


class SubscribeView(APIView):
    """POST /v1/subscribe/ — initialise a Paystack transaction.

    Returns an authorization_url the client redirects the user to.
    Paystack calls /v1/paystack/webhook/ when payment completes.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SubscribeSerializer,
        responses={200: {"type": "object"}},
        summary="Subscribe to Plus via Paystack",
        description=(
            "Initialises a Paystack transaction for the selected plan. "
            "Returns {authorization_url, reference, payment_id}. "
            "Redirect the user to authorization_url to complete payment. "
            "Paystack will POST a charge.success event to /v1/paystack/webhook/ when done."
        ),
    )
    def post(self, request):
        ser = SubscribeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        plan_code = ser.validated_data["plan_code"]

        try:
            plan = Plan.objects.get(code=plan_code)
        except Plan.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": f"Plan '{plan_code}' not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Ensure subscription record exists (or create it)
        subscription, _ = Subscription.objects.get_or_create(
            user=request.user,
            defaults={"plan": plan, "status": Subscription.Status.ACTIVE},
        )
        if subscription.plan_id != plan_code:
            subscription.plan = plan
            subscription.save(update_fields=["plan", "updated_at"])

        # Create payment record — its UUID becomes the Paystack reference
        payment = Payment.objects.create(
            user=request.user,
            subscription=subscription,
            provider="paystack",
            # reference is set to payment.id after creation (UUID is the idempotency key)
            provider_ref="INIT",  # placeholder; updated below
            amount_kes=plan.price_kes,
            status=Payment.Status.PENDING,
        )
        # Use the payment UUID as the Paystack reference (guarantees idempotency)
        payment.provider_ref = str(payment.id)
        payment.save(update_fields=["provider_ref"])

        # Initialise Paystack transaction
        paystack_result = _initialize_paystack_transaction(
            email=request.user.email or f"user-{request.user.id}@flavorfind.internal",
            amount_kes=plan.price_kes,
            reference=str(payment.id),
            metadata={
                "payment_id": str(payment.id),
                "plan_code": plan_code,
                "user_id": str(request.user.id),
            },
        )

        return Response(
            {
                "payment_id": str(payment.id),
                "reference": str(payment.id),
                "authorization_url": paystack_result.get("authorization_url"),
                "access_code": paystack_result.get("access_code"),
                "status": "pending",
                "message": "Redirect the user to authorization_url to complete payment.",
            }
        )


class PaystackWebhookView(APIView):
    """POST /v1/paystack/webhook/ — Paystack event webhook.

    Paystack sends a POST with a JSON body signed with HMAC-SHA512.
    We verify the X-Paystack-Signature header before processing.

    Security:
      1. Signature verified with HMAC-SHA512(PAYSTACK_SECRET_KEY, raw_body)
      2. Amount re-verified server-side — never trust the webhook amount alone
      3. Reference (payment UUID) used for idempotency — duplicate events ignored
      4. Returns 200 always (Paystack retries on non-200)
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # no JWT on this endpoint

    @extend_schema(
        request=None,
        responses={200: {"type": "object"}},
        summary="Paystack payment webhook",
        description=(
            "Paystack event webhook. Verified by HMAC-SHA512 signature. "
            "Processes charge.success events to activate subscriptions."
        ),
    )
    def post(self, request):
        # Always return 200 — Paystack retries on non-200
        try:
            self._process_event(request)
        except Exception as exc:
            logger.error("Paystack webhook processing error: %s", exc)
        return Response({"status": "ok"})

    def _process_event(self, request):
        # 1. Verify HMAC-SHA512 signature
        raw_body = request.body
        signature = request.META.get("HTTP_X_PAYSTACK_SIGNATURE", "")

        if not _verify_paystack_signature(raw_body, signature):
            logger.warning(
                "Paystack webhook: invalid signature. Ignoring event."
            )
            return

        body = request.data
        event = body.get("event", "")

        if event != "charge.success":
            # We only care about successful charges
            logger.debug("Paystack webhook: ignoring event %s", event)
            return

        data = body.get("data", {})
        reference = data.get("reference", "")
        amount_kobo = int(data.get("amount", 0))  # Paystack amounts are in kobo (1/100 KES)
        amount_kes = amount_kobo / 100
        paystack_id = str(data.get("id", ""))
        gateway_response = data.get("gateway_response", "")

        logger.info(
            "Paystack charge.success: reference=%s amount_kes=%s gateway=%s",
            reference,
            amount_kes,
            gateway_response,
        )

        # 2. Look up payment by reference (= payment UUID)
        try:
            payment = (
                Payment.objects.filter(provider_ref=reference)
                .select_related("subscription", "user")
                .get()
            )
        except Payment.DoesNotExist:
            logger.warning("Paystack webhook: no payment found for reference %s", reference)
            return

        # 3. Idempotency — already confirmed, ignore
        if payment.status == Payment.Status.CONFIRMED:
            logger.info("Paystack webhook: payment %s already confirmed — ignoring.", reference)
            return

        # 4. Re-verify amount (SAFETY: never trust webhook amount alone)
        expected = float(payment.amount_kes)
        if abs(amount_kes - expected) > 0.01:
            logger.error(
                "Paystack webhook AMOUNT MISMATCH: expected %.2f, got %.2f (ref %s)",
                expected,
                amount_kes,
                reference,
            )
            return

        # 5. Confirm payment and activate subscription
        client_ip = _get_client_ip(request)

        payment.status = Payment.Status.CONFIRMED
        payment.receipt_no = paystack_id
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=["status", "receipt_no", "confirmed_at"])

        subscription = payment.subscription
        subscription.status = Subscription.Status.ACTIVE
        from datetime import timedelta
        subscription.renews_at = timezone.now() + timedelta(days=30)
        subscription.save(update_fields=["status", "renews_at", "updated_at"])

        log_audit_event(
            action="payment_confirmed",
            actor_id=payment.user_id,
            actor_type="user",
            object_type="payment",
            object_id=payment.id,
            after_data={
                "paystack_id": paystack_id,
                "amount_kes": amount_kes,
                "reference": reference,
            },
            ip_address=client_ip,
        )

        logger.info(
            "Plus activated for user %s via Paystack ref %s (paystack_id=%s)",
            payment.user_id,
            reference,
            paystack_id,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_paystack_signature(raw_body: bytes, signature: str) -> bool:
    """Verify Paystack HMAC-SHA512 webhook signature."""
    secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", "")
    if not secret_key:
        logger.error("PAYSTACK_SECRET_KEY is not set — cannot verify webhook signature.")
        return False

    expected = hmac.new(
        secret_key.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _initialize_paystack_transaction(
    email: str,
    amount_kes: float,
    reference: str,
    metadata: dict | None = None,
) -> dict:
    """Call Paystack Initialize Transaction API.

    POST https://api.paystack.co/transaction/initialize
    Authorization: Bearer PAYSTACK_SECRET_KEY

    Returns the Paystack response dict containing:
      - authorization_url: redirect the user here
      - access_code: for Paystack Popup (inline checkout)
      - reference: echoes back our reference
    """
    import requests as http

    secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", "")

    if not secret_key:
        # Dev/test fallback — return a mock response
        logger.warning("PAYSTACK_SECRET_KEY not set. Returning mock Paystack response.")
        return {
            "authorization_url": f"https://checkout.paystack.com/mock-{reference[:8]}",
            "access_code": f"mock_access_{reference[:8]}",
            "reference": reference,
        }

    # Paystack amounts are in the smallest currency unit.
    # For KES: Paystack uses KES natively (not kobo like NGN).
    # Amount is in KES cents — multiply by 100.
    amount_kobo = int(float(amount_kes) * 100)

    payload = {
        "email": email,
        "amount": amount_kobo,
        "reference": reference,
        "currency": "KES",
        "callback_url": getattr(
            settings,
            "PAYSTACK_CALLBACK_URL",
            "https://flavorfind.co.ke/plus/success",
        ),
        "metadata": metadata or {},
    }

    try:
        resp = http.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("status"):
            raise ValueError(f"Paystack error: {result.get('message')}")
        return result.get("data", {})
    except Exception as exc:
        logger.error("Paystack initialize error: %s", exc)
        raise


def _get_client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
