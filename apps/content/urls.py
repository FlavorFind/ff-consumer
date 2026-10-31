"""URL patterns for the content app."""

from django.urls import path

from apps.content import views

urlpatterns = [
    path("regions/", views.RegionsView.as_view(), name="regions"),
    path("stories/", views.StoryListView.as_view(), name="stories"),
    path("stories/<slug:slug>/", views.StoryDetailView.as_view(), name="story-detail"),
]
