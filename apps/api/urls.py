"""URL router for /v1/ — the consumer API."""

from django.urls import include, path

from apps.api import views

urlpatterns = [
    # Public
    path("health/", views.HealthView.as_view(), name="health"),
    path("meta/version/", views.MetaVersionView.as_view(), name="meta-version"),

    # Auth + user + devices
    path("", include("apps.accounts.urls")),

    # Profile + diet
    path("", include("apps.profiles.urls")),

    # Pantry
    path("", include("apps.pantry.urls")),

    # Search, resolve, ingredients, dishes
    path("", include("apps.search.urls")),

    # Library — saved recipes, collections, cook log
    path("", include("apps.library.urls")),

    # Planner — meal plans, shopping lists
    path("", include("apps.planner.urls")),

    # Budget mode
    path("", include("apps.budget.urls")),

    # Content — regions, stories
    path("", include("apps.content.urls")),

    # Offline sync
    path("", include("apps.sync.urls")),

    # Community — submissions, reviews
    path("", include("apps.community.urls")),

    # Billing — plans, subscribe, Paystack webhook, subscription status
    path("", include("apps.billing.urls")),

    # Notifications — in-app, preferences
    path("", include("apps.notifications.urls")),
]
