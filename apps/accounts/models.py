"""User models for ff-consumer."""

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """Manager for CustomUser — email-based accounts only."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("A user must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
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
        extra_fields.setdefault("email_verified", True)
        if not extra_fields["is_staff"]:
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email=email, password=password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Consumer user model. Email + password only."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DELETED = "deleted", "Deleted"

    class Language(models.TextChoices):
        EN = "en", "English"
        SW = "sw", "Swahili"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.EN)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    email_verified = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self):
        """Mark the user as deleted. Actual data purge happens via Celery."""
        self.status = self.Status.DELETED
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=["status", "deleted_at", "is_active", "updated_at"])


class EmailVerification(models.Model):
    """Stores email verification tokens sent via Resend."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="email_verifications"
    )
    token = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "email verification"
        verbose_name_plural = "email verifications"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None


class AuthIdentity(models.Model):
    """Tracks which login methods a user has set up."""

    class Provider(models.TextChoices):
        PASSWORD = "password", "Email + Password"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="identities")
    provider = models.CharField(max_length=20, choices=Provider.choices)
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
    version = models.CharField(max_length=20)
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "consent"
        verbose_name_plural = "consents"
