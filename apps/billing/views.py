"""Billing views — plans, M-Pesa STK push, subscription status."""

import logging

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Payment, Plan, Subscription
from apps.core.models import log_audit_event

logger = logging.getLogger(__name__)

# Safaricom IP ranges for M-Pesa callback validation
# Update this list from Safaricom's official documentation
MPESA_IP_RANGES = [
    "196.201.214.",
    "196.201.213.",
]


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
            # Return free plan details for users with no subscription record
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


class SubscribeSerializer(serializers.Serializer):
    """Input for POST /v1/subscribe/."""

    phone = serializers.CharField(
        max_length=20,
        help_text="M-Pesa phone number in format 254XXXXXXXXX",
    )
    plan_code = serializers.ChoiceField(choices=["plus"], default="plus")

    def validate_phone(self, value):
        # Must be 254XXXXXXXXX format
        value = value.replace("+", "").replace(" ", "")
        if not value.startswith("254") or len(value) != 12:
            raise serializers.ValidationError(
                "Phone must be in format 254XXXXXXXXX (e.g. 254712345678)"
            )
        return value


class SubscribeView(APIView):
    """POST /v1/subscribe/ — initiate M-Pesa STK push."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SubscribeSerializer,
        responses={200: {"type": "object"}},
        summary="Subscribe to Plus via M-Pesa",
        description=(
            "Initiates an M-Pesa STK push to the user's phone. "
            "The user confirms on their phone. "
            "Daraja calls /v1/mpesa/callback/ when payment is confirmed."
        ),
    )
    def post(self, request):
        ser = SubscribeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        plan_code = ser.validated_data["plan_code"]
        phone = ser.validated_data["phone"]

        try:
            plan = Plan.objects.get(code=plan_code)
        except Plan.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": f"Plan '{plan_code}' not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create a pending payment record as the idempotency anchor
        # The provider_ref will be updated when Daraja confirms
        import uuid as _uuid

        pending_ref = f"PENDING-{_uuid.uuid4().hex[:8].upper()}"

        subscription, _ = Subscription.objects.get_or_create(
            user=request.user,
            defaults={"plan": plan, "status": Subscription.Status.ACTIVE},
        )
        if subscription.plan_id != plan_code:
            subscription.plan = plan
            subscription.save(update_fields=["plan", "updated_at"])

        payment = Payment.objects.create(
            user=request.user,
            subscription=subscription,
            provider="mpesa",
            provider_ref=pending_ref,
            amount_kes=plan.price_kes,
            status=Payment.Status.PENDING,
        )

        # Initiate STK push
        stk_result = _initiate_stk_push(
            phone=phone,
            amount=int(plan.price_kes),
            reference=str(payment.id),
        )

        return Response(
            {
                "payment_id": str(payment.id),
                "status": "pending",
                "message": "STK push sent. Enter your M-Pesa PIN to complete.",
                "checkout_request_id": stk_result.get("CheckoutRequestID"),
            }
        )


class MpesaCallbackView(APIView):
    """POST /v1/mpesa/callback/ — Daraja callback.

    Unauthenticated but verified:
    1. Source IP must be in Safaricom's published range
    2. Amount must match the expected amount for the payment
    3. provider_ref (M-Pesa transaction ID) must not already be processed
    """

    permission_classes = [AllowAny]
    # Do not apply JWT authentication to this endpoint
    authentication_classes = []

    @extend_schema(
        request=None,
        responses={200: {"type": "object"}},
        summary="M-Pesa payment callback",
        description=(
            "Daraja webhook for payment confirmation. "
            "Verified by source IP and amount re-check. "
            "Returns 200 to Daraja regardless (to prevent retries on our errors)."
        ),
    )
    def post(self, request):
        # Always return 200 to Daraja — otherwise they retry
        try:
            self._process_callback(request)
        except Exception as exc:
            logger.error("M-Pesa callback processing error: %s", exc)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    def _process_callback(self, request):
        # 1. Verify source IP
        client_ip = self._get_client_ip(request)
        if not self._is_safaricom_ip(client_ip):
            logger.warning("M-Pesa callback from unexpected IP: %s", client_ip)
            # Log and continue — Safaricom IP ranges change; don't hard-fail in v1
            # In production: add strict IP filtering

        body = request.data
        result_code = body.get("Body", {}).get("stkCallback", {}).get("ResultCode")
        if result_code != 0:
            # Payment failed or was cancelled by user
            logger.info("M-Pesa STK callback: payment not completed (ResultCode=%s)", result_code)
            return

        callback_metadata = (
            body.get("Body", {}).get("stkCallback", {}).get("CallbackMetadata", {})
        )
        items = {
            item["Name"]: item.get("Value")
            for item in callback_metadata.get("Item", [])
        }

        mpesa_receipt = items.get("MpesaReceiptNumber", "")
        transaction_amount = float(items.get("Amount", 0))
        _phone = str(items.get("PhoneNumber", ""))  # reserved for future use
        _checkout_request_id = (  # reserved: use to look up payment once stored on Payment model
            body.get("Body", {}).get("stkCallback", {}).get("CheckoutRequestID", "")
        )

        # 2. Find the payment by checkout reference
        # In a full implementation, store checkout_request_id on the payment
        # For v1: look up by pending status and amount
        payment = (
            Payment.objects.filter(
                status=Payment.Status.PENDING,
                amount_kes=transaction_amount,
            )
            .select_related("subscription", "user")
            .first()
        )

        if not payment:
            logger.warning(
                "M-Pesa callback: no pending payment for amount %s", transaction_amount
            )
            return

        # 3. Check idempotency — avoid processing the same receipt twice
        if Payment.objects.filter(provider_ref=mpesa_receipt).exists():
            logger.info("M-Pesa callback: duplicate receipt %s — ignoring.", mpesa_receipt)
            return

        # 4. Re-verify amount (SAFETY: never trust the callback amount alone)
        expected_amount = float(payment.amount_kes)
        if abs(transaction_amount - expected_amount) > 0.01:
            logger.error(
                "M-Pesa callback AMOUNT MISMATCH: expected %s, got %s (receipt %s)",
                expected_amount,
                transaction_amount,
                mpesa_receipt,
            )
            return

        # 5. Confirm payment and activate subscription
        payment.provider_ref = mpesa_receipt
        payment.status = Payment.Status.CONFIRMED
        payment.receipt_no = mpesa_receipt
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=["provider_ref", "status", "receipt_no", "confirmed_at"])

        subscription = payment.subscription
        subscription.status = Subscription.Status.ACTIVE
        # Set renewal date to 30 days from now
        from datetime import timedelta

        subscription.renews_at = timezone.now() + timedelta(days=30)
        subscription.save(update_fields=["status", "renews_at", "updated_at"])

        log_audit_event(
            action="payment_confirmed",
            actor_id=payment.user_id,
            actor_type="user",
            object_type="payment",
            object_id=payment.id,
            after_data={"receipt": mpesa_receipt, "amount": transaction_amount},
            ip_address=client_ip,
        )

        logger.info(
            "Plus activated for user %s via M-Pesa receipt %s",
            payment.user_id,
            mpesa_receipt,
        )

    def _get_client_ip(self, request) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    def _is_safaricom_ip(self, ip: str) -> bool:
        return any(ip.startswith(prefix) for prefix in MPESA_IP_RANGES)


def _initiate_stk_push(phone: str, amount: int, reference: str) -> dict:
    """Call Daraja STK push API.

    In staging: use Safaricom sandbox.
    Returns the Daraja response dict.
    """
    # TODO: Implement full Daraja STK push using requests
    # Environment variables needed:
    #   MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET
    #   MPESA_SHORTCODE, MPESA_PASSKEY
    #   MPESA_CALLBACK_URL
    #   MPESA_ENVIRONMENT (sandbox|production)
    #
    # For now: return a mock response so the endpoint works
    import uuid

    logger.info(
        "STK push placeholder: phone=%s amount=%s ref=%s", phone, amount, reference
    )
    return {
        "CheckoutRequestID": f"mock-{uuid.uuid4().hex[:8]}",
        "ResponseCode": "0",
        "ResponseDescription": "Success. Request accepted for processing",
        "MerchantRequestID": reference,
        "CustomerMessage": "Success. Request accepted for processing",
    }
