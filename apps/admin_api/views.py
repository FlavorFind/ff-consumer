"""
Consumer Admin API views.

All endpoints require the ADMIN_API_SERVICE_TOKEN (Bearer auth).
Mounted at /v1/admin/ in config/urls.py.

Authentication: Authorization: Bearer <ADMIN_API_SERVICE_TOKEN>
"""

import logging

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status as http_status

from apps.accounts.models import CustomUser
from apps.billing.models import Payment, Plan, Subscription
from apps.community.models import Review, Submission
from apps.content.models import Story
from apps.core.models import AuditEvent, log_audit_event
from apps.partners.models import SponsoredSlot

from .authentication import ServiceTokenAuthentication
from .serializers import (
    AuditEventSerializer,
    CreateSlotSerializer,
    CreateStorySerializer,
    GrantPlusSerializer,
    PatchSlotSerializer,
    PatchStorySerializer,
    PatchSubscriptionSerializer,
    PatchUserSerializer,
    PaymentListSerializer,
    ReviewActionSerializer,
    ReviewDetailSerializer,
    ReviewListSerializer,
    ReviewSubmissionActionSerializer,
    SponsoredSlotSerializer,
    StoryDetailSerializer,
    StoryListSerializer,
    SubmissionDetailSerializer,
    SubmissionListSerializer,
    SubscriptionListSerializer,
    UserDetailSerializer,
    UserListSerializer,
)

logger = logging.getLogger(__name__)

_auth = [ServiceTokenAuthentication]
_perm = [IsAuthenticated]


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _paginate(request, queryset, serializer_class):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@extend_schema(tags=["admin:users"], summary="List all users")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def user_list(request):
    qs = CustomUser.objects.select_related("subscription").order_by("-created_at")
    if status_f := request.query_params.get("status"):
        qs = qs.filter(status=status_f)
    if plan := request.query_params.get("subscription_plan"):
        qs = qs.filter(subscription__plan_id=plan)
    if verified := request.query_params.get("email_verified"):
        qs = qs.filter(email_verified=(verified.lower() == "true"))
    if search := request.query_params.get("search"):
        qs = qs.filter(Q(email__icontains=search) | Q(username__icontains=search))
    return _paginate(request, qs, UserListSerializer)


@extend_schema(tags=["admin:users"], summary="Get user detail")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def user_detail(request, user_id):
    try:
        user = (
            CustomUser.objects.select_related("subscription__plan")
            .prefetch_related("devices", "identities", "consents", "subscription__payments")
            .get(pk=user_id)
        )
    except CustomUser.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    return Response(UserDetailSerializer(user).data)


@extend_schema(tags=["admin:users"], summary="Update user fields (status, email_verified, language)")
@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def user_update(request, user_id):
    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    ser = PatchUserSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)

    before = {}
    after = {}
    update_fields = []
    for field, value in ser.validated_data.items():
        old = getattr(user, field)
        if old != value:
            before[field] = str(old)
            after[field] = str(value)
            setattr(user, field, value)
            update_fields.append(field)

    if update_fields:
        update_fields.append("updated_at")
        user.save(update_fields=update_fields)
        log_audit_event(
            actor_type=AuditEvent.ActorType.STAFF,
            action="admin_update_user",
            object_type="user",
            object_id=user.pk,
            before_data=before,
            after_data=after,
        )
    return Response(UserDetailSerializer(user).data)


@extend_schema(tags=["admin:users"], summary="Force email verification")
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def user_verify_email(request, user_id):
    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    if user.email_verified:
        return Response({"message": "Email already verified."})
    user.email_verified = True
    user.save(update_fields=["email_verified", "updated_at"])
    log_audit_event(
        actor_type=AuditEvent.ActorType.STAFF,
        action="admin_force_verify_email",
        object_type="user",
        object_id=user.pk,
    )
    return Response({"email_verified": True})


# ---------------------------------------------------------------------------
# Subscriptions & Billing
# ---------------------------------------------------------------------------


@extend_schema(tags=["admin:billing"], summary="List all subscriptions")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def subscription_list(request):
    qs = Subscription.objects.select_related("user", "plan").order_by("-created_at")
    if status_f := request.query_params.get("status"):
        qs = qs.filter(status=status_f)
    if plan_f := request.query_params.get("plan"):
        qs = qs.filter(plan_id=plan_f)
    return _paginate(request, qs, SubscriptionListSerializer)


@extend_schema(tags=["admin:billing"], summary="Get subscription detail with payment history")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def subscription_detail(request, sub_id):
    from .serializers import SubscriptionSerializer
    try:
        sub = Subscription.objects.select_related("user", "plan").prefetch_related("payments").get(pk=sub_id)
    except Subscription.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    return Response(SubscriptionSerializer(sub).data)


@extend_schema(tags=["admin:billing"], summary="Update subscription (manual grant, cancel, extend)")
@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def subscription_update(request, sub_id):
    from .serializers import SubscriptionSerializer
    try:
        sub = Subscription.objects.select_related("user", "plan").get(pk=sub_id)
    except Subscription.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    ser = PatchSubscriptionSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)

    before = {}
    after = {}
    update_fields = []
    reason = ser.validated_data.pop("reason", "")
    for field, value in ser.validated_data.items():
        old = getattr(sub, field)
        if old != value:
            before[field] = str(old)
            after[field] = str(value)
            setattr(sub, field, value)
            update_fields.append(field)

    if update_fields:
        update_fields.append("updated_at")
        sub.save(update_fields=update_fields)
        log_audit_event(
            actor_type=AuditEvent.ActorType.STAFF,
            action="admin_update_subscription",
            object_type="subscription",
            object_id=sub.pk,
            before_data=before,
            after_data=after,
            reason=reason,
        )
    return Response(SubscriptionSerializer(sub).data)


@extend_schema(tags=["admin:billing"], summary="Manually grant Plus subscription to a user")
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def subscription_grant_plus(request):
    from datetime import timedelta
    from .serializers import SubscriptionSerializer

    ser = GrantPlusSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)

    try:
        user = CustomUser.objects.get(pk=ser.validated_data["user_id"])
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found."}, status=http_status.HTTP_404_NOT_FOUND)

    plus_plan = Plan.objects.get(code="plus")
    days = ser.validated_data.get("days", 30)
    reason = ser.validated_data.get("reason", "")

    with transaction.atomic():
        sub, _ = Subscription.objects.get_or_create(
            user=user, defaults={"plan": plus_plan, "status": "active"}
        )
        sub.plan = plus_plan
        sub.status = "active"
        sub.renews_at = timezone.now() + timedelta(days=days)
        sub.cancelled_at = None
        sub.save(update_fields=["plan", "status", "renews_at", "cancelled_at", "updated_at"])
        log_audit_event(
            actor_type=AuditEvent.ActorType.STAFF,
            action="admin_grant_plus",
            object_type="subscription",
            object_id=sub.pk,
            after_data={"plan": "plus", "days": days, "renews_at": str(sub.renews_at)},
            reason=reason or f"Plus granted manually for {days} days",
        )

    return Response(SubscriptionSerializer(sub).data)


@extend_schema(tags=["admin:billing"], summary="List all payments")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def payment_list(request):
    qs = Payment.objects.select_related("user").order_by("-created_at")
    if status_f := request.query_params.get("status"):
        qs = qs.filter(status=status_f)
    if user_id := request.query_params.get("user_id"):
        qs = qs.filter(user_id=user_id)
    return _paginate(request, qs, PaymentListSerializer)


@extend_schema(tags=["admin:billing"], summary="Billing summary stats")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def billing_stats(request):
    total_users = CustomUser.objects.filter(status="active").count()
    active_plus = Subscription.objects.filter(plan_id="plus", status="active").count()
    trialing = Subscription.objects.filter(plan_id="plus", status="trialing").count()
    confirmed_payments = Payment.objects.filter(status="confirmed")
    total_revenue_kes = confirmed_payments.aggregate(total=Sum("amount_kes"))["total"] or 0

    return Response(
        {
            "total_active_users": total_users,
            "active_plus_subscribers": active_plus,
            "trialing_users": trialing,
            "total_revenue_kes": str(total_revenue_kes),
            "confirmed_payments": confirmed_payments.count(),
        }
    )


# ---------------------------------------------------------------------------
# Moderation — Submissions
# ---------------------------------------------------------------------------


@extend_schema(tags=["admin:moderation"], summary="List community recipe submissions")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def submission_list(request):
    qs = Submission.objects.select_related("user").order_by("-created_at")
    if status_f := request.query_params.get("status"):
        qs = qs.filter(status=status_f)
    if user_id := request.query_params.get("user_id"):
        qs = qs.filter(user_id=user_id)
    return _paginate(request, qs, SubmissionListSerializer)


@extend_schema(tags=["admin:moderation"], summary="Get submission detail")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def submission_detail(request, submission_id):
    try:
        sub = Submission.objects.select_related("user").get(pk=submission_id)
    except Submission.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    return Response(SubmissionDetailSerializer(sub).data)


@extend_schema(tags=["admin:moderation"], summary="Approve or reject a submission")
@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def submission_review(request, submission_id):
    try:
        sub = Submission.objects.select_related("user").get(pk=submission_id)
    except Submission.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)

    ser = ReviewSubmissionActionSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)

    action = ser.validated_data["action"]
    reason = ser.validated_data.get("reason", "")

    with transaction.atomic():
        if action == "approve":
            sub.status = "sent"  # signals it's been forwarded to engine
        else:
            sub.status = "rejected"
            sub.reason = reason
        sub.save(update_fields=["status", "reason", "updated_at"])
        log_audit_event(
            actor_type=AuditEvent.ActorType.STAFF,
            action=f"admin_{action}_submission",
            object_type="submission",
            object_id=sub.pk,
            reason=reason,
        )
    return Response(SubmissionDetailSerializer(sub).data)


# ---------------------------------------------------------------------------
# Moderation — Reviews
# ---------------------------------------------------------------------------


@extend_schema(tags=["admin:moderation"], summary="List dish reviews")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def review_list(request):
    qs = Review.objects.select_related("user").order_by("-created_at")
    if status_f := request.query_params.get("status"):
        qs = qs.filter(status=status_f)
    if dish_slug := request.query_params.get("dish_slug"):
        qs = qs.filter(dish_slug=dish_slug)
    if stars := request.query_params.get("stars"):
        qs = qs.filter(stars=int(stars))
    return _paginate(request, qs, ReviewListSerializer)


@extend_schema(tags=["admin:moderation"], summary="Get review detail")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def review_detail(request, review_id):
    try:
        review = Review.objects.select_related("user").get(pk=review_id)
    except Review.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    return Response(ReviewDetailSerializer(review).data)


@extend_schema(tags=["admin:moderation"], summary="Approve or reject a review")
@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def review_action(request, review_id):
    try:
        review = Review.objects.get(pk=review_id)
    except Review.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)

    ser = ReviewActionSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)

    action = ser.validated_data["action"]
    reason = ser.validated_data.get("reason", "")

    with transaction.atomic():
        if action == "approve":
            review.status = "approved"
        else:
            review.status = "rejected"
            review.reason = reason
        review.save(update_fields=["status", "reason", "updated_at"])
        log_audit_event(
            actor_type=AuditEvent.ActorType.STAFF,
            action=f"admin_{action}_review",
            object_type="review",
            object_id=review.pk,
            reason=reason,
        )
    return Response(ReviewDetailSerializer(review).data)


# ---------------------------------------------------------------------------
# Editorial Stories
# ---------------------------------------------------------------------------


@extend_schema(tags=["admin:stories"], summary="List editorial stories")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def story_list(request):
    qs = Story.objects.order_by("-created_at")
    if status_f := request.query_params.get("status"):
        qs = qs.filter(status=status_f)
    if search := request.query_params.get("search"):
        qs = qs.filter(
            Q(title_en__icontains=search) | Q(title_sw__icontains=search)
        )
    return _paginate(request, qs, StoryListSerializer)


@extend_schema(tags=["admin:stories"], summary="Create a story")
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def story_create(request):
    ser = CreateStorySerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)
    data = ser.validated_data
    if data.get("status") == "published":
        data["published_at"] = timezone.now()
    story = Story.objects.create(**data)
    log_audit_event(
        actor_type=AuditEvent.ActorType.STAFF,
        action="admin_create_story",
        object_type="story",
        object_id=story.pk,
        after_data={"title_en": story.title_en, "status": story.status},
    )
    return Response(StoryDetailSerializer(story).data, status=http_status.HTTP_201_CREATED)


@extend_schema(tags=["admin:stories"], summary="Get story detail")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def story_detail(request, slug):
    try:
        story = Story.objects.get(slug=slug)
    except Story.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    return Response(StoryDetailSerializer(story).data)


@extend_schema(tags=["admin:stories"], summary="Update a story")
@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def story_update(request, slug):
    try:
        story = Story.objects.get(slug=slug)
    except Story.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    ser = PatchStorySerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)

    update_fields = []
    for field, value in ser.validated_data.items():
        setattr(story, field, value)
        update_fields.append(field)
    if "status" in ser.validated_data and ser.validated_data["status"] == "published":
        if not story.published_at:
            story.published_at = timezone.now()
            update_fields.append("published_at")

    if update_fields:
        update_fields.append("updated_at")
        story.save(update_fields=update_fields)
    return Response(StoryDetailSerializer(story).data)


@extend_schema(tags=["admin:stories"], summary="Delete a story")
@api_view(["DELETE"])
@authentication_classes(_auth)
@permission_classes(_perm)
def story_delete(request, slug):
    try:
        story = Story.objects.get(slug=slug)
    except Story.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    log_audit_event(
        actor_type=AuditEvent.ActorType.STAFF,
        action="admin_delete_story",
        object_type="story",
        object_id=story.pk,
        before_data={"title_en": story.title_en},
    )
    story.delete()
    return Response(status=http_status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["admin:stories"], summary="Publish a story")
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def story_publish(request, slug):
    try:
        story = Story.objects.get(slug=slug)
    except Story.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    story.status = "published"
    story.published_at = story.published_at or timezone.now()
    story.save(update_fields=["status", "published_at", "updated_at"])
    return Response(StoryDetailSerializer(story).data)


@extend_schema(tags=["admin:stories"], summary="Archive a story")
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def story_archive(request, slug):
    try:
        story = Story.objects.get(slug=slug)
    except Story.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    story.status = "archived"
    story.save(update_fields=["status", "updated_at"])
    return Response(StoryDetailSerializer(story).data)


# ---------------------------------------------------------------------------
# Sponsored Slots
# ---------------------------------------------------------------------------


@extend_schema(tags=["admin:slots"], summary="List sponsored slots")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def slot_list(request):
    qs = SponsoredSlot.objects.order_by("-created_at")
    if is_active := request.query_params.get("is_active"):
        qs = qs.filter(is_active=(is_active.lower() == "true"))
    if slot_type := request.query_params.get("type"):
        qs = qs.filter(sponsored_type=slot_type)
    return _paginate(request, qs, SponsoredSlotSerializer)


@extend_schema(tags=["admin:slots"], summary="Create a sponsored slot")
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def slot_create(request):
    ser = CreateSlotSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)
    slot = SponsoredSlot.objects.create(**ser.validated_data)
    log_audit_event(
        actor_type=AuditEvent.ActorType.STAFF,
        action="admin_create_slot",
        object_type="sponsored_slot",
        object_id=slot.pk,
        after_data={"partner_name": slot.partner_name, "engine_slug": slot.engine_slug},
    )
    return Response(SponsoredSlotSerializer(slot).data, status=http_status.HTTP_201_CREATED)


@extend_schema(tags=["admin:slots"], summary="Get slot detail")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def slot_detail(request, slot_id):
    try:
        slot = SponsoredSlot.objects.get(pk=slot_id)
    except SponsoredSlot.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    return Response(SponsoredSlotSerializer(slot).data)


@extend_schema(tags=["admin:slots"], summary="Update a sponsored slot")
@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def slot_update(request, slot_id):
    try:
        slot = SponsoredSlot.objects.get(pk=slot_id)
    except SponsoredSlot.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    ser = PatchSlotSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=http_status.HTTP_400_BAD_REQUEST)
    update_fields = []
    for field, value in ser.validated_data.items():
        setattr(slot, field, value)
        update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        slot.save(update_fields=update_fields)
    return Response(SponsoredSlotSerializer(slot).data)


@extend_schema(tags=["admin:slots"], summary="Delete a sponsored slot")
@api_view(["DELETE"])
@authentication_classes(_auth)
@permission_classes(_perm)
def slot_delete(request, slot_id):
    try:
        slot = SponsoredSlot.objects.get(pk=slot_id)
    except SponsoredSlot.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    slot.delete()
    return Response(status=http_status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["admin:slots"], summary="Activate a slot")
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def slot_activate(request, slot_id):
    try:
        slot = SponsoredSlot.objects.get(pk=slot_id)
    except SponsoredSlot.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    slot.is_active = True
    slot.save(update_fields=["is_active", "updated_at"])
    return Response(SponsoredSlotSerializer(slot).data)


@extend_schema(tags=["admin:slots"], summary="Deactivate a slot")
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def slot_deactivate(request, slot_id):
    try:
        slot = SponsoredSlot.objects.get(pk=slot_id)
    except SponsoredSlot.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    slot.is_active = False
    slot.save(update_fields=["is_active", "updated_at"])
    return Response(SponsoredSlotSerializer(slot).data)


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


@extend_schema(tags=["admin:audit"], summary="Paginated audit log (read-only)")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def audit_list(request):
    qs = AuditEvent.objects.order_by("-created_at")
    if actor_id := request.query_params.get("actor_id"):
        qs = qs.filter(actor_id=actor_id)
    if action := request.query_params.get("action"):
        qs = qs.filter(action=action)
    if obj_type := request.query_params.get("object_type"):
        qs = qs.filter(object_type=obj_type)
    return _paginate(request, qs, AuditEventSerializer)


@extend_schema(tags=["admin:audit"], summary="Get audit event detail")
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def audit_detail(request, event_id):
    try:
        event = AuditEvent.objects.get(pk=event_id)
    except AuditEvent.DoesNotExist:
        return Response({"error": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
    return Response(AuditEventSerializer(event).data)
