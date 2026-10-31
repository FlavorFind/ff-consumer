"""Business logic for accounts — email verification, token generation."""

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import EmailVerification

logger = logging.getLogger(__name__)

User = get_user_model()

EMAIL_VERIFY_TTL_HOURS = 24


def _generate_token() -> str:
    """Generate a secure random hex token."""
    return secrets.token_hex(32)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def send_verification_email(user) -> None:
    """Create an email verification token and send it via Resend.

    The plain token is emailed to the user. Only the SHA-256 hash is stored.
    """
    # Invalidate any existing unused tokens for this user
    EmailVerification.objects.filter(user=user, used_at__isnull=True).delete()

    token = _generate_token()
    EmailVerification.objects.create(
        user=user,
        token=_hash_token(token),
        expires_at=timezone.now() + timedelta(hours=EMAIL_VERIFY_TTL_HOURS),
    )

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"

    _send_via_resend(
        to=user.email,
        subject="Verify your Flavor Find email",
        html=f"""
        <p>Hi {user.username},</p>
        <p>Thanks for signing up for Flavor Find!</p>
        <p>Click the link below to verify your email address. The link expires in 24 hours.</p>
        <p><a href="{verify_url}" style="background:#e85d04;color:#fff;padding:12px 24px;
           border-radius:4px;text-decoration:none;display:inline-block;">
           Verify my email</a></p>
        <p>Or copy this link into your browser:<br>{verify_url}</p>
        <p>If you didn't create an account, you can ignore this email.</p>
        <p>— The Flavor Find team</p>
        """,
    )


def verify_email_token(token: str) -> User:
    """Verify the email token and mark the user's email as verified.

    Returns the user on success. Raises ValueError with a user-safe message on failure.
    """
    token_hash = _hash_token(token)

    try:
        verification = EmailVerification.objects.select_related("user").get(
            token=token_hash,
            used_at__isnull=True,
        )
    except EmailVerification.DoesNotExist:
        raise ValueError("Invalid or already used verification link.") from None

    if verification.is_expired:
        raise ValueError("This verification link has expired. Please request a new one.")

    # Mark token used and user verified
    verification.used_at = timezone.now()
    verification.save(update_fields=["used_at"])

    user = verification.user
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
    """Send a transactional email via the Resend API.

    Requires RESEND_API_KEY in settings.
    From address is set to RESEND_FROM_EMAIL (default: onboarding@resend.dev for dev).
    """
    import requests as http_requests

    api_key = getattr(settings, "RESEND_API_KEY", "")
    from_email = getattr(settings, "RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if not api_key:
        # No key configured — log and skip (safe for test environments)
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
        logger.info("Verification email sent to %s via Resend (id: %s)", to, resp.json().get("id"))
    except Exception as exc:
        # Email failure should not break registration — log and continue
        logger.error("Failed to send verification email to %s: %s", to, exc)
