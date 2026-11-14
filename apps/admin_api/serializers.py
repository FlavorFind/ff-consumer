"""
Serializers for the Consumer Admin API.
Explicit field lists — no auto-generation.
"""

from rest_framework import serializers

from apps.accounts.models import AuthIdentity, Consent, CustomUser, Device
from apps.billing.models import Payment, Plan, Subscription
from apps.community.models import Review, Submission
from apps.content.models import Story
from apps.core.models import AuditEvent
from apps.partners.models import SponsoredSlot


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserListSerializer(serializers.ModelSerializer):
    subscription_plan = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "username",
            "language",
            "status",
            "email_verified",
            "subscription_plan",
            "subscription_status",
            "created_at",
            "last_login",
        ]
        read_only_fields = fields

    def get_subscription_plan(self, obj):
        try:
            return obj.subscription.plan_id
        except Exception:
            return "free"

    def get_subscription_status(self, obj):
        try:
            return obj.subscription.status
        except Exception:
            return "none"


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["id", "platform", "last_seen", "last_sync_at", "created_at"]
        read_only_fields = fields


class AuthIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthIdentity
        fields = ["provider", "verified_at", "created_at"]
        read_only_fields = fields


class ConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consent
        fields = ["type", "version", "granted_at", "revoked_at"]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "provider",
            "provider_ref",
            "amount_kes",
            "status",
            "receipt_no",
            "created_at",
            "confirmed_at",
        ]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan_id",
            "plan_name",
            "status",
            "trial_ends_at",
            "renews_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "payments",
        ]
        read_only_fields = fields


class UserDetailSerializer(serializers.ModelSerializer):
    devices = DeviceSerializer(many=True, read_only=True)
    identities = AuthIdentitySerializer(many=True, read_only=True)
    consents = ConsentSerializer(many=True, read_only=True)
    subscription = SubscriptionSerializer(read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "username",
            "language",
            "status",
            "email_verified",
            "is_staff",
            "created_at",
            "updated_at",
            "deleted_at",
            "last_login",
            "devices",
            "identities",
            "consents",
            "subscription",
        ]
        read_only_fields = fields


class PatchUserSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["active", "suspended", "deleted"], required=False
    )
    email_verified = serializers.BooleanField(required=False)
    language = serializers.ChoiceField(choices=["en", "sw"], required=False)


class GrantPlusSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    days = serializers.IntegerField(min_value=1, required=False, default=30)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# Subscriptions & Billing
# ---------------------------------------------------------------------------


class SubscriptionListSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "user_email",
            "plan_id",
            "plan_name",
            "status",
            "trial_ends_at",
            "renews_at",
            "cancelled_at",
            "created_at",
        ]
        read_only_fields = fields


class PatchSubscriptionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["pending", "active", "trialing", "cancelled", "expired"], required=False
    )
    plan_id = serializers.ChoiceField(choices=["free", "plus"], required=False)
    renews_at = serializers.DateTimeField(required=False, allow_null=True)
    trial_ends_at = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class PaymentListSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "user_email",
            "provider",
            "provider_ref",
            "amount_kes",
            "status",
            "receipt_no",
            "created_at",
            "confirmed_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Moderation — Submissions
# ---------------------------------------------------------------------------


class SubmissionListSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "user_email",
            "status",
            "engine_submission_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SubmissionDetailSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "user_email",
            "payload",
            "engine_submission_id",
            "status",
            "reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ReviewSubmissionActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")

    def validate(self, data):
        if data["action"] == "reject" and not data.get("reason", "").strip():
            raise serializers.ValidationError(
                {"reason": "A reason is required when rejecting."}
            )
        return data


# ---------------------------------------------------------------------------
# Moderation — Reviews
# ---------------------------------------------------------------------------


class ReviewListSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Review
        fields = [
            "id",
            "user_email",
            "dish_slug",
            "dish_id",
            "stars",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class ReviewDetailSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Review
        fields = [
            "id",
            "user_email",
            "dish_slug",
            "dish_id",
            "stars",
            "text",
            "status",
            "reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ReviewActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")

    def validate(self, data):
        if data["action"] == "reject" and not data.get("reason", "").strip():
            raise serializers.ValidationError({"reason": "A reason is required when rejecting."})
        return data


# ---------------------------------------------------------------------------
# Editorial Stories
# ---------------------------------------------------------------------------


class StoryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Story
        fields = [
            "id",
            "slug",
            "title_en",
            "title_sw",
            "status",
            "author",
            "published_at",
            "created_at",
        ]
        read_only_fields = fields


class StoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Story
        fields = [
            "id",
            "slug",
            "title_en",
            "title_sw",
            "body_en",
            "body_sw",
            "region_slugs",
            "author",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "published_at", "created_at", "updated_at"]


class CreateStorySerializer(serializers.Serializer):
    title_en = serializers.CharField(max_length=300)
    title_sw = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    body_en = serializers.CharField()
    body_sw = serializers.CharField(required=False, allow_blank=True, default="")
    region_slugs = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    author = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=["draft", "published", "archived"], required=False, default="draft"
    )


class PatchStorySerializer(serializers.Serializer):
    title_en = serializers.CharField(max_length=300, required=False)
    title_sw = serializers.CharField(max_length=300, required=False, allow_blank=True)
    body_en = serializers.CharField(required=False)
    body_sw = serializers.CharField(required=False, allow_blank=True)
    region_slugs = serializers.CharField(max_length=500, required=False, allow_blank=True)
    author = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=["draft", "published", "archived"], required=False
    )


# ---------------------------------------------------------------------------
# Sponsored Slots
# ---------------------------------------------------------------------------


class SponsoredSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = SponsoredSlot
        fields = [
            "id",
            "partner_name",
            "sponsored_type",
            "engine_id",
            "engine_slug",
            "display_name",
            "label",
            "starts_at",
            "ends_at",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CreateSlotSerializer(serializers.Serializer):
    partner_name = serializers.CharField(max_length=200)
    sponsored_type = serializers.ChoiceField(choices=["dish", "ingredient"])
    engine_id = serializers.CharField(max_length=36)
    engine_slug = serializers.CharField(max_length=200)
    display_name = serializers.CharField(max_length=300)
    label = serializers.CharField(max_length=50, default="Sponsored")
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    is_active = serializers.BooleanField(default=True)

    def validate(self, data):
        if data["starts_at"] >= data["ends_at"]:
            raise serializers.ValidationError(
                {"ends_at": "ends_at must be after starts_at."}
            )
        return data


class PatchSlotSerializer(serializers.Serializer):
    partner_name = serializers.CharField(max_length=200, required=False)
    display_name = serializers.CharField(max_length=300, required=False)
    label = serializers.CharField(max_length=50, required=False)
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
    is_active = serializers.BooleanField(required=False)


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor_id",
            "actor_type",
            "action",
            "object_type",
            "object_id",
            "before_data",
            "after_data",
            "reason",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields
