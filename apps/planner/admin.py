"""Admin for planner app."""

from django.contrib import admin

from apps.planner.models import MealPlan, MealPlanEntry, ShoppingItem, ShoppingList


class MealPlanEntryInline(admin.TabularInline):
    model = MealPlanEntry
    extra = 0


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ["user", "week_start", "created_at"]
    raw_id_fields = ["user"]
    inlines = [MealPlanEntryInline]


class ShoppingItemInline(admin.TabularInline):
    model = ShoppingItem
    extra = 0
    readonly_fields = ["ingredient_id", "ingredient_slug"]


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = ["user", "name", "plan", "created_at"]
    raw_id_fields = ["user", "plan"]
    inlines = [ShoppingItemInline]
