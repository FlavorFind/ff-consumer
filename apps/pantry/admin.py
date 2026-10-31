"""Admin for pantry app."""

from django.contrib import admin

from apps.pantry.models import PantryItem


@admin.register(PantryItem)
class PantryItemAdmin(admin.ModelAdmin):
    list_display = ["user", "display_name", "ingredient_slug", "added_at", "expires_on"]
    list_filter = []
    raw_id_fields = ["user"]
    search_fields = ["display_name", "ingredient_slug", "user__email"]
    readonly_fields = ["added_at"]
