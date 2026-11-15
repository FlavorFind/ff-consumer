"""Business logic for accounts — email verification via OTP."""

import hashlib
import logging
import random
import string
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import CustomUser, EmailVerification

logger = logging.getLogger(__name__)

User = get_user_model()

OTP_TTL_MINUTES = 10
OTP_LENGTH = 6


def _generate_otp() -> str:
    """Generate a 6-digit numeric OTP."""
    return "".join(random.choices(string.digits, k=OTP_LENGTH))


def _hash_otp(otp: str, user_id: str) -> str:
    """Hash OTP + user_id together so the same code for different users never collides."""
    return hashlib.sha256(f"{otp}:{user_id}".encode()).hexdigest()


def send_verification_email(user) -> None:
    """Generate a 6-digit OTP and email it to the user.

    The plain OTP is emailed. Only the SHA-256 hash (salted with user_id) is stored.
    """
    # Invalidate any existing unused OTPs for this user
    EmailVerification.objects.filter(user=user, used_at__isnull=True).delete()

    otp = _generate_otp()
    EmailVerification.objects.create(
        user=user,
        token=_hash_otp(otp, str(user.id)),
        expires_at=timezone.now() + timedelta(minutes=OTP_TTL_MINUTES),
    )

    _send_via_resend(
        to=user.email,
        subject="Your Flavor Find verification code",
        html=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:2rem;">
          <h2 style="color:#0d1f14;margin-bottom:.5rem;">Verify your email</h2>
          <p style="color:#444;margin-bottom:1.5rem;">
            Hi {user.username}, enter this code in the Flavor Find app to verify your email.
            It expires in {OTP_TTL_MINUTES} minutes.
          </p>
          <div style="background:#f4f4f4;border-radius:8px;padding:1.5rem;text-align:center;
                      letter-spacing:0.3em;font-size:2.5rem;font-weight:700;
                      color:#0d1f14;font-family:monospace;">
            {otp}
          </div>
          <p style="color:#888;font-size:0.85rem;margin-top:1.5rem;">
            If you didn't create a Flavor Find account, you can ignore this email.
          </p>
        </div>
        """,
    )


def verify_email_otp(email: str, otp: str) -> CustomUser:
    """Verify the OTP and mark the user's email as verified.

    Returns the user on success. Raises ValueError with a user-safe message on failure.
    """
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        raise ValueError("Invalid code. Please try again.") from None

    token_hash = _hash_otp(otp.strip(), str(user.id))

    try:
        verification = EmailVerification.objects.select_related("user").get(
            user=user,
            token=token_hash,
            used_at__isnull=True,
        )
    except EmailVerification.DoesNotExist:
        raise ValueError("Invalid code. Please try again.") from None

    if verification.is_expired:
        raise ValueError("This code has expired. Request a new one.")

    verification.used_at = timezone.now()
    verification.save(update_fields=["used_at"])

    user.email_verified = True
    user.save(update_fields=["email_verified", "updated_at"])

    return user


def get_tokens_for_user(user) -> dict:
    """Generate JWT access + refresh token pair for a user."""
    refresh = RefreshToken.for_user(user)
    refresh["language"] = user.language
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def _send_via_resend(to: str, subject: str, html: str) -> None:
    """Send a transactional email via the Resend API."""
    import requests as http_requests

    api_key = getattr(settings, "RESEND_API_KEY", "")
    from_email = getattr(settings, "RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if not api_key:
        logger.warning("RESEND_API_KEY not set — skipping email to %s (subject: %s)", to, subject)
        return

    try:
        resp = http_requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Verification OTP sent to %s via Resend (id: %s)", to, resp.json().get("id"))
    except Exception as exc:
        logger.error("Failed to send verification OTP to %s: %s", to, exc)
