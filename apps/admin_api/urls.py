"""
URL configuration for the Consumer Admin API.
Mounted at /v1/admin/ in config/urls.py.
All endpoints require the ADMIN_API_SERVICE_TOKEN (Bearer auth).
"""

from django.urls import path

from . import views

urlpatterns = [
    # Users
    path("users/", views.user_list, name="admin-user-list"),
    path("users/<uuid:user_id>/", views.user_detail, name="admin-user-detail"),
    path("users/<uuid:user_id>/update/", views.user_update, name="admin-user-update"),
    path("users/<uuid:user_id>/verify-email/", views.user_verify_email, name="admin-user-verify-email"),
    # Subscriptions & Billing
    path("subscriptions/", views.subscription_list, name="admin-subscription-list"),
    path("subscriptions/<uuid:sub_id>/", views.subscription_detail, name="admin-subscription-detail"),
    path("subscriptions/<uuid:sub_id>/update/", views.subscription_update, name="admin-subscription-update"),
    path("subscriptions/grant-plus/", views.subscription_grant_plus, name="admin-subscription-grant-plus"),
    path("payments/", views.payment_list, name="admin-payment-list"),
    path("billing/stats/", views.billing_stats, name="admin-billing-stats"),
    # Moderation — Submissions
    path("moderation/submissions/", views.submission_list, name="admin-submission-list"),
    path("moderation/submissions/<uuid:submission_id>/", views.submission_detail, name="admin-submission-detail"),
    path("moderation/submissions/<uuid:submission_id>/review/", views.submission_review, name="admin-submission-review"),
    # Moderation — Reviews
    path("moderation/reviews/", views.review_list, name="admin-review-list"),
    path("moderation/reviews/<uuid:review_id>/", views.review_detail, name="admin-review-detail"),
    path("moderation/reviews/<uuid:review_id>/action/", views.review_action, name="admin-review-action"),
    # Editorial Stories
    path("stories/", views.story_list, name="admin-story-list"),
    path("stories/create/", views.story_create, name="admin-story-create"),
    path("stories/<slug:slug>/", views.story_detail, name="admin-story-detail"),
    path("stories/<slug:slug>/update/", views.story_update, name="admin-story-update"),
    path("stories/<slug:slug>/delete/", views.story_delete, name="admin-story-delete"),
    path("stories/<slug:slug>/publish/", views.story_publish, name="admin-story-publish"),
    path("stories/<slug:slug>/archive/", views.story_archive, name="admin-story-archive"),
    # Sponsored Slots
    path("slots/", views.slot_list, name="admin-slot-list"),
    path("slots/create/", views.slot_create, name="admin-slot-create"),
    path("slots/<uuid:slot_id>/", views.slot_detail, name="admin-slot-detail"),
    path("slots/<uuid:slot_id>/update/", views.slot_update, name="admin-slot-update"),
    path("slots/<uuid:slot_id>/delete/", views.slot_delete, name="admin-slot-delete"),
    path("slots/<uuid:slot_id>/activate/", views.slot_activate, name="admin-slot-activate"),
    path("slots/<uuid:slot_id>/deactivate/", views.slot_deactivate, name="admin-slot-deactivate"),
    # Audit Log
    path("audit/", views.audit_list, name="admin-audit-list"),
    path("audit/<uuid:event_id>/", views.audit_detail, name="admin-audit-detail"),
]
