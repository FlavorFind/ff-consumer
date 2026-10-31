"""Admin for library app."""

from django.contrib import admin

from apps.library.models import Collection, CookLog, SavedRecipe


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["user", "name", "created_at"]
    raw_id_fields = ["user"]
    search_fields = ["name", "user__email"]


@admin.register(SavedRecipe)
class SavedRecipeAdmin(admin.ModelAdmin):
    list_display = ["user", "dish_slug", "dataset_version", "collection", "saved_at"]
    list_filter = ["dataset_version"]
    raw_id_fields = ["user", "collection"]
    search_fields = ["dish_slug", "user__email"]
    readonly_fields = ["saved_at"]


@admin.register(CookLog)
class CookLogAdmin(admin.ModelAdmin):
    list_display = ["user", "dish_slug", "rating", "cooked_at"]
    raw_id_fields = ["user"]
    readonly_fields = ["cooked_at"]
