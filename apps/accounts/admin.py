"""Admin configuration for accounts — 2FA required."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django_otp.admin import OTPAdminSite

from apps.accounts.models import AuthIdentity, Consent, CustomUser, Device, EmailVerification

# Replace the default admin site with the OTP-protected version
admin.site.__class__ = OTPAdminSite


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = [
        "email",
        "username",
        "language",
        "status",
        "email_verified",
        "is_staff",
        "created_at",
    ]
    list_filter = ["status", "language", "is_staff", "is_active", "email_verified"]
    search_fields = ["email", "username"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Personal", {"fields": ("language",)}),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "email_verified",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "deleted_at",
                )
            },
        ),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
        ("Dates", {"fields": ("created_at", "updated_at", "last_login")}),
    )
    readonly_fields = ["created_at", "updated_at", "last_login"]

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "password1", "password2", "language"),
            },
        ),
    )


@admin.register(AuthIdentity)
class AuthIdentityAdmin(admin.ModelAdmin):
    list_display = ["user", "provider", "verified_at", "created_at"]
    list_filter = ["provider"]
    search_fields = ["user__email", "user__username"]
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


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "expires_at", "used_at"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    readonly_fields = ["token", "created_at"]
