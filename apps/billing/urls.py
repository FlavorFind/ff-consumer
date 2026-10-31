"""URL patterns for the billing app."""

from django.urls import path

from apps.billing import views

urlpatterns = [
    path("plans/", views.PlanListView.as_view(), name="billing-plans"),
    path("subscription/", views.SubscriptionView.as_view(), name="subscription"),
    path("subscribe/", views.SubscribeView.as_view(), name="subscribe"),
    path("mpesa/callback/", views.MpesaCallbackView.as_view(), name="mpesa-callback"),
]
