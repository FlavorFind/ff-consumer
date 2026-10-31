"""URL patterns for the pantry app."""

from django.urls import path

from apps.pantry import views

urlpatterns = [
    path("pantry/", views.PantryView.as_view(), name="pantry"),
    path("pantry/<uuid:item_id>/", views.PantryItemDetailView.as_view(), name="pantry-item"),
]
