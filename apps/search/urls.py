"""URL patterns for the search app."""

from django.urls import path

from apps.search import views

urlpatterns = [
    path("search/", views.SearchView.as_view(), name="search"),
    path("resolve/", views.ResolveView.as_view(), name="resolve"),
    path("ingredients/", views.IngredientsView.as_view(), name="ingredients"),
    path("dishes/<slug:slug>/", views.DishDetailView.as_view(), name="dish-detail"),
]
