"""Business logic for accounts — OTP, token generation, user creation."""

import hashlib
import logging
import random
import string
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuthIdentity, Consent, OTPRequest

logger = logging.getLogger(__name__)

User = get_user_model()

OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_MINUTES = 1  # minimum gap between requests for same phone


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _generate_otp_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def request_otp(phone: str) -> OTPRequest:
    """Create a new OTP for the given phone number.

    Rate-limited: raises ValueError if a valid, unused OTP already exists
    and was created within OTP_COOLDOWN_MINUTES.
    """
    recent = (
        OTPRequest.objects.filter(
            phone=phone,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
            created_at__gt=timezone.now() - timedelta(minutes=OTP_COOLDOWN_MINUTES),
        )
        .order_by("-created_at")
        .first()
    )
    if recent:
        raise ValueError("Please wait before requesting another code.")

    code = _generate_otp_code()
    otp = OTPRequest.objects.create(
        phone=phone,
        code_hash=_hash_code(code),
        expires_at=timezone.now() + timedelta(minutes=OTP_TTL_MINUTES),
    )

    # TODO: integrate with SMS gateway (Africa's Talking or similar)
    # For now: log the code (development only — remove before production)
    logger.warning("OTP for %s: %s [REMOVE IN PRODUCTION]", phone, code)

    return otp


def verify_otp(phone: str, code: str) -> User:
    """Verify the OTP code and return (or create) the user.

    Raises ValueError with a user-safe message on any failure.
    """
    otp = (
        OTPRequest.objects.filter(phone=phone, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    if not otp:
        raise ValueError("No pending verification code. Please request a new one.")

    if otp.is_expired:
        raise ValueError("The code has expired. Please request a new one.")

    if otp.is_locked:
        raise ValueError("Too many incorrect attempts. Please request a new code.")

    if otp.code_hash != _hash_code(code):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        remaining = OTP_MAX_ATTEMPTS - otp.attempts
        raise ValueError(f"Incorrect code. {remaining} attempt(s) remaining.")

    # Code is correct — mark it used
    otp.used_at = timezone.now()
    otp.save(update_fields=["used_at"])

    # Get or create the user
    user, created = User.objects.get_or_create(
        phone=phone,
        defaults={"status": User.Status.ACTIVE},
    )

    if created:
        AuthIdentity.objects.create(
            user=user,
            provider=AuthIdentity.Provider.PHONE_OTP,
            verified_at=timezone.now(),
        )
        Consent.objects.create(user=user, type=Consent.ConsentType.TERMS, version="2026-10")
        Consent.objects.create(user=user, type=Consent.ConsentType.PRIVACY, version="2026-10")
        logger.info("New user created via phone OTP: %s", phone)
    else:
        # Ensure the phone_otp identity exists
        AuthIdentity.objects.get_or_create(
            user=user,
            provider=AuthIdentity.Provider.PHONE_OTP,
            defaults={"verified_at": timezone.now()},
        )

    return user


def get_tokens_for_user(user: User) -> dict:
    """Generate JWT access + refresh token pair for a user."""
    refresh = RefreshToken.for_user(user)
    refresh["language"] = user.language
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }
