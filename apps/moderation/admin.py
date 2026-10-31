"""Moderation admin — review queue for community submissions and dish reviews.

Moderators work exclusively through the Django admin.
Step-up re-auth is enforced for approve/reject actions (see custom action methods).

Audit events are logged for every approve/reject action.
"""

import logging

from django.contrib import admin, messages

from apps.community.models import Review, Submission

logger = logging.getLogger(__name__)


class ModerationAdminMixin:
    """Shared helpers for submission/review moderation admin views."""

    def _require_step_up(self, request) -> bool:
        """Step-up 2FA check — returns True if user has recently re-authed.

        In v1: check that django-otp has verified the staff member's OTP device
        within the last 30 minutes. If not, redirect to the OTP verify page.
        """
        from django.utils import timezone
        from django_otp import user_has_device, verify_token  # noqa: F401

        if not request.user.is_verified():
            return False

        # Additional recency check: last_verified stored in session
        last_verified = request.session.get("otp_last_verified")
        if not last_verified:
            return False

        from datetime import timedelta

        cutoff = timezone.now() - timedelta(minutes=30)
        # last_verified is an ISO timestamp string
        import datetime

        try:
            lv = datetime.datetime.fromisoformat(last_verified)
            if lv.tzinfo is None:
                lv = lv.replace(tzinfo=datetime.UTC)
            return lv >= cutoff
        except (ValueError, TypeError):
            return False


@admin.register(Submission)
class SubmissionModerationAdmin(ModerationAdminMixin, admin.ModelAdmin):
    """Moderation queue for community recipe submissions.

    Available actions:
      - approve_and_forward: approves the submission and queues Celery task
        to forward to engine. Requires step-up 2FA.
      - reject_submissions: rejects with a reason (set in payload).
        Requires step-up 2FA.
    """

    list_display = [
        "get_recipe_name",
        "user",
        "status",
        "created_at",
        "updated_at",
        "engine_submission_id",
    ]
    list_filter = ["status", "created_at"]
    raw_id_fields = ["user"]
    readonly_fields = ["created_at", "updated_at", "engine_submission_id", "user"]
    search_fields = ["user__email"]
    ordering = ["-created_at"]
    actions = ["approve_and_forward", "reject_submissions"]

    def get_queryset(self, request):
        # Default to pending/draft submissions in the moderation view
        qs = super().get_queryset(request)
        return qs.select_related("user")

    def get_recipe_name(self, obj):
        return obj.payload.get("name_en", "—") if obj.payload else "—"

    get_recipe_name.short_description = "Recipe Name"

    def approve_and_forward(self, request, queryset):
        """Approve selected submissions and forward to engine via Celery.

        Requires step-up 2FA within the last 30 minutes.
        """
        if not self._require_step_up(request):
            self.message_user(
                request,
                "Step-up authentication required. Please re-verify your OTP.",
                level=messages.ERROR,
            )
            return

        from apps.community.tasks import forward_submission_to_engine
        from apps.core.models import AuditEvent, log_audit_event

        count = 0
        for submission in queryset.filter(status=Submission.Status.DRAFT):
            log_audit_event(
                action="submission_approved",
                actor_id=str(request.user.id),
                actor_type=AuditEvent.ActorType.STAFF,
                object_type="submission",
                object_id=str(submission.id),
                before_data={"status": submission.status},
                after_data={"status": "sent"},
                ip_address=request.META.get("REMOTE_ADDR", ""),
            )
            submission.status = Submission.Status.SENT
            submission.save(update_fields=["status", "updated_at"])
            forward_submission_to_engine.delay(str(submission.id))
            count += 1

        self.message_user(
            request, f"{count} submission(s) approved and queued for engine forwarding."
        )

    approve_and_forward.short_description = "✅ Approve and forward to engine"

    def reject_submissions(self, request, queryset):
        """Reject selected submissions.

        Requires step-up 2FA within the last 30 minutes.
        """
        if not self._require_step_up(request):
            self.message_user(
                request,
                "Step-up authentication required. Please re-verify your OTP.",
                level=messages.ERROR,
            )
            return

        from apps.core.models import AuditEvent, log_audit_event

        count = 0
        for submission in queryset.exclude(status=Submission.Status.REJECTED):
            log_audit_event(
                action="submission_rejected",
                actor_id=str(request.user.id),
                actor_type=AuditEvent.ActorType.STAFF,
                object_type="submission",
                object_id=str(submission.id),
                before_data={"status": submission.status},
                after_data={"status": "rejected"},
                ip_address=request.META.get("REMOTE_ADDR", ""),
            )
            submission.status = Submission.Status.REJECTED
            submission.save(update_fields=["status", "updated_at"])
            count += 1

        self.message_user(request, f"{count} submission(s) rejected.")

    reject_submissions.short_description = "❌ Reject submissions"


@admin.register(Review)
class ReviewModerationAdmin(ModerationAdminMixin, admin.ModelAdmin):
    """Moderation queue for dish reviews.

    Available actions:
      - approve_reviews: publishes the reviews.
      - reject_reviews: hides the reviews.
    Both require step-up 2FA.
    """

    list_display = ["user", "dish_slug", "stars", "status", "created_at"]
    list_filter = ["status", "stars", "created_at"]
    raw_id_fields = ["user"]
    readonly_fields = ["created_at", "updated_at", "user"]
    search_fields = ["user__email", "dish_slug"]
    ordering = ["-created_at"]
    actions = ["approve_reviews", "reject_reviews"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    def approve_reviews(self, request, queryset):
        if not self._require_step_up(request):
            self.message_user(
                request,
                "Step-up authentication required. Please re-verify your OTP.",
                level=messages.ERROR,
            )
            return

        from apps.core.models import AuditEvent, log_audit_event

        count = 0
        for review in queryset.filter(status=Review.Status.PENDING):
            log_audit_event(
                action="review_approved",
                actor_id=str(request.user.id),
                actor_type=AuditEvent.ActorType.STAFF,
                object_type="review",
                object_id=str(review.id),
                before_data={"status": review.status},
                after_data={"status": Review.Status.APPROVED},
                ip_address=request.META.get("REMOTE_ADDR", ""),
            )
            count += 1

        queryset.filter(status=Review.Status.PENDING).update(status=Review.Status.APPROVED)
        self.message_user(request, f"{count} review(s) approved.")

    approve_reviews.short_description = "✅ Approve reviews"

    def reject_reviews(self, request, queryset):
        if not self._require_step_up(request):
            self.message_user(
                request,
                "Step-up authentication required. Please re-verify your OTP.",
                level=messages.ERROR,
            )
            return

        from apps.core.models import AuditEvent, log_audit_event

        count = 0
        for review in queryset.exclude(status=Review.Status.REJECTED):
            log_audit_event(
                action="review_rejected",
                actor_id=str(request.user.id),
                actor_type=AuditEvent.ActorType.STAFF,
                object_type="review",
                object_id=str(review.id),
                before_data={"status": review.status},
                after_data={"status": Review.Status.REJECTED},
                ip_address=request.META.get("REMOTE_ADDR", ""),
            )
            count += 1

        queryset.exclude(status=Review.Status.REJECTED).update(status=Review.Status.REJECTED)
        self.message_user(request, f"{count} review(s) rejected.")

    reject_reviews.short_description = "❌ Reject reviews"
