"""URL patterns for the budget app."""

from django.urls import path

from apps.budget import views

urlpatterns = [
    path("budget/suggest/", views.BudgetSuggestView.as_view(), name="budget-suggest"),
]
