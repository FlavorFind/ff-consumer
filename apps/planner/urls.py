"""URL patterns for the planner app."""

from django.urls import path

from apps.planner import views

urlpatterns = [
    path("plans/<str:week>/", views.MealPlanView.as_view(), name="meal-plan"),
    path(
        "plans/<uuid:plan_id>/shopping-list/",
        views.ShoppingListGenerateView.as_view(),
        name="shopping-list-generate",
    ),
    path(
        "shopping-lists/<uuid:list_id>/",
        views.ShoppingListDetailView.as_view(),
        name="shopping-list",
    ),
    path(
        "shopping-lists/<uuid:list_id>/items/<uuid:item_id>/",
        views.ShoppingItemCheckView.as_view(),
        name="shopping-item",
    ),
    path(
        "shopping-lists/<uuid:list_id>/share/",
        views.ShoppingListShareView.as_view(),
        name="shopping-list-share",
    ),
]
