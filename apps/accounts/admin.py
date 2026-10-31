"""Admin configuration for accounts — 2FA required."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django_otp.admin import OTPAdminSite

from apps.accounts.models import AuthIdentity, Consent, CustomUser, Device, OTPRequest

# Replace the default admin site with the OTP-protected version
admin.site.__class__ = OTPAdminSite


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ["email", "phone", "language", "status", "is_staff", "created_at"]
    list_filter = ["status", "language", "is_staff", "is_active"]
    search_fields = ["email", "phone"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("email", "phone", "password")}),
        ("Personal", {"fields": ("language",)}),
        ("Status", {"fields": ("status", "is_active", "is_staff", "is_superuser", "deleted_at")}),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
        ("Dates", {"fields": ("created_at", "updated_at", "last_login")}),
    )
    readonly_fields = ["created_at", "updated_at", "last_login"]

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "phone", "password1", "password2", "language"),
        }),
    )


@admin.register(AuthIdentity)
class AuthIdentityAdmin(admin.ModelAdmin):
    list_display = ["user", "provider", "verified_at", "created_at"]
    list_filter = ["provider"]
    search_fields = ["user__email", "user__phone"]
    raw_id_fields = ["user"]


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "last_seen", "last_sync_at", "created_at"]
    list_filter = ["platform"]
    raw_id_fields = ["user"]


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ["user", "type", "version", "granted_at", "revoked_at"]
    list_filter = ["type"]
    raw_id_fields = ["user"]
    readonly_fields = ["granted_at"]


@admin.register(OTPRequest)
class OTPRequestAdmin(admin.ModelAdmin):
    list_display = ["phone", "attempts", "created_at", "expires_at", "used_at"]
    list_filter = []
    search_fields = ["phone"]
    readonly_fields = ["code_hash", "created_at"]
