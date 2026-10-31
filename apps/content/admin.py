"""Admin for content app."""

from django.contrib import admin

from apps.content.models import Story


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ["title_en", "status", "author", "published_at", "created_at"]
    list_filter = ["status"]
    search_fields = ["title_en", "title_sw", "region_slugs", "author"]
    prepopulated_fields = {"slug": ("title_en",)}
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("slug", "status", "author", "region_slugs", "published_at")}),
        ("English", {"fields": ("title_en", "body_en")}),
        ("Swahili", {"fields": ("title_sw", "body_sw"), "classes": ("collapse",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
