"""User models for ff-consumer."""

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """Manager for CustomUser — supports email-based and phone-based accounts."""

    def create_user(self, email=None, phone=None, password=None, **extra_fields):
        if not email and not phone:
            raise ValueError("A user must have either an email or a phone number.")
        if email:
            email = self.normalize_email(email)
        user = self.model(email=email, phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", CustomUser.Status.ACTIVE)
        if not extra_fields["is_staff"]:
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email=email, password=password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Consumer user model.

    Supports both email+password and phone OTP login.
    Phone numbers are stored encrypted (handled at the view/service layer).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DELETED = "deleted", "Deleted"

    class Language(models.TextChoices):
        EN = "en", "English"
        SW = "sw", "Swahili"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, null=True, blank=True)
    # Phone stored as a string; encryption at the application layer for field-level security.
    # Format: E.164 (e.g. +254712345678)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.EN)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email or self.phone or str(self.id)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self):
        """Mark the user as deleted. Actual data purge happens via Celery."""
        self.status = self.Status.DELETED
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=["status", "deleted_at", "is_active", "updated_at"])


class AuthIdentity(models.Model):
    """Tracks which login methods a user has set up."""

    class Provider(models.TextChoices):
        PASSWORD = "password", "Email + Password"
        PHONE_OTP = "phone_otp", "Phone OTP"
        GOOGLE = "google", "Google"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="identities")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_uid = models.CharField(max_length=255, null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "provider")]
        verbose_name = "auth identity"
        verbose_name_plural = "auth identities"


class Device(models.Model):
    """A device associated with a user — tracks push tokens and sync state."""

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        WEB = "web", "Web"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="devices")
    platform = models.CharField(max_length=10, choices=Platform.choices)
    push_token = models.TextField(null=True, blank=True)
    last_seen = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "device"
        verbose_name_plural = "devices"


class Consent(models.Model):
    """Records user consent to terms, privacy policy, and marketing."""

    class ConsentType(models.TextChoices):
        TERMS = "terms", "Terms of Service"
        PRIVACY = "privacy", "Privacy Policy"
        MARKETING = "marketing", "Marketing Communications"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="consents")
    type = models.CharField(max_length=20, choices=ConsentType.choices)
    version = models.CharField(max_length=20)  # e.g. "2026-10"
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "consent"
        verbose_name_plural = "consents"


class OTPRequest(models.Model):
    """Tracks phone OTP requests — for throttling and verification."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20, db_index=True)
    # Code is stored hashed. Plain code is sent to user and never stored.
    code_hash = models.CharField(max_length=128)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "OTP request"
        verbose_name_plural = "OTP requests"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_locked(self) -> bool:
        """Locked after MAX_ATTEMPTS failed attempts."""
        return self.attempts >= 5
