"""Admin for billing app."""

from django.contrib import admin

from apps.billing.models import Payment, Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "price_kes", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "status", "renews_at", "created_at"]
    list_filter = ["status", "plan"]
    raw_id_fields = ["user"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["user", "amount_kes", "provider", "status", "created_at", "confirmed_at"]
    list_filter = ["status", "provider"]
    raw_id_fields = ["user", "subscription"]
    readonly_fields = ["created_at", "confirmed_at", "provider_ref"]
    search_fields = ["provider_ref", "receipt_no"]
