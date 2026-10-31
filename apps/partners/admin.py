"""Admin for partners app."""

from django.contrib import admin

from apps.partners.models import SponsoredSlot


@admin.register(SponsoredSlot)
class SponsoredSlotAdmin(admin.ModelAdmin):
    list_display = [
        "partner_name",
        "display_name",
        "sponsored_type",
        "starts_at",
        "ends_at",
        "is_active",
    ]
    list_filter = ["sponsored_type", "is_active"]
    search_fields = ["partner_name", "display_name", "engine_id", "engine_slug"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "partner_name",
                    "sponsored_type",
                    "engine_id",
                    "engine_slug",
                    "display_name",
                    "label",
                    "is_active",
                )
            },
        ),
        ("Schedule", {"fields": ("starts_at", "ends_at")}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
