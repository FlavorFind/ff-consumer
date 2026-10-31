"""URL patterns for the community app."""

from django.urls import path

from apps.community import views

urlpatterns = [
    path("submissions/", views.SubmissionListView.as_view(), name="submissions"),
    path(
        "submissions/<uuid:submission_id>/",
        views.SubmissionDetailView.as_view(),
        name="submission-detail",
    ),
    path(
        "dishes/<slug:slug>/reviews/",
        views.DishReviewView.as_view(),
        name="dish-reviews",
    ),
]
