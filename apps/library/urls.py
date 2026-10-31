"""URL patterns for the library app."""

from django.urls import path

from apps.library import views

urlpatterns = [
    path("saved/", views.SavedRecipeListView.as_view(), name="saved-recipes"),
    path("saved/<uuid:recipe_id>/", views.SavedRecipeDetailView.as_view(), name="saved-recipe"),
    path("saved/collections/", views.CollectionListView.as_view(), name="collections"),
    path(
        "saved/collections/<uuid:col_id>/",
        views.CollectionDetailView.as_view(),
        name="collection",
    ),
    path("cooked/", views.CookLogListView.as_view(), name="cook-log"),
]
