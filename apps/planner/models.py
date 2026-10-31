"""Planner models — meal plans, shopping lists."""

import uuid

from django.conf import settings
from django.db import models


class MealPlan(models.Model):
    """A weekly meal plan. Identified externally by ISO week (YYYY-Www)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meal_plans"
    )
    # week_start is always a Monday
    week_start = models.DateField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "week_start")]
        ordering = ["-week_start"]

    def __str__(self):
        return f"{self.user} — week of {self.week_start}"


class MealPlanEntry(models.Model):
    """One dish in a meal plan — one day, one meal type."""

    class Day(models.TextChoices):
        MON = "mon", "Monday"
        TUE = "tue", "Tuesday"
        WED = "wed", "Wednesday"
        THU = "thu", "Thursday"
        FRI = "fri", "Friday"
        SAT = "sat", "Saturday"
        SUN = "sun", "Sunday"

    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "Breakfast"
        LUNCH = "lunch", "Lunch"
        DINNER = "dinner", "Dinner"
        SNACK = "snack", "Snack"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(MealPlan, on_delete=models.CASCADE, related_name="entries")
    day = models.CharField(max_length=3, choices=Day.choices)
    meal_type = models.CharField(max_length=10, choices=MealType.choices)
    dish_id = models.CharField(max_length=36)  # engine UUID
    dish_slug = models.CharField(max_length=200)
    servings = models.PositiveIntegerField(default=1)
    note = models.TextField(blank=True, default="")
    position = models.PositiveIntegerField(default=0)  # ordering within day+meal_type

    class Meta:
        ordering = ["day", "meal_type", "position"]

    def __str__(self):
        return f"{self.plan} — {self.day} {self.meal_type}: {self.dish_slug}"


class ShoppingList(models.Model):
    """A shopping list. Optionally linked to a meal plan."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_lists"
    )
    plan = models.ForeignKey(
        MealPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="shopping_lists"
    )
    name = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.name or 'Shopping List'}"


class ShoppingItem(models.Model):
    """One item on a shopping list."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="items")
    ingredient_id = models.CharField(max_length=36)
    ingredient_slug = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200)
    quantity_note = models.CharField(max_length=200, blank=True, default="")
    checked = models.BooleanField(default=False)
    # Price estimate from engine cost data — always labelled as estimate
    price_estimate_kes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "display_name"]

    def __str__(self):
        return f"{self.display_name} ({'✓' if self.checked else '○'})"
