"""Serializers for the accounts app."""

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Add user language to the JWT payload."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["language"] = user.language
        return token


class RegisterSerializer(serializers.Serializer):
    """Registration: email + username + password."""

    email = serializers.EmailField()
    username = serializers.CharField(min_length=3, max_length=50)
    password = serializers.CharField(write_only=True, min_length=8)
    language = serializers.ChoiceField(choices=["en", "sw"], default="en")
    terms_version = serializers.CharField(default="2026-10")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        # Only letters, numbers, underscores, hyphens
        import re

        if not re.match(r"^[\w-]+$", value):
            raise serializers.ValidationError(
                "Username may only contain letters, numbers, underscores, and hyphens."
            )
        return value

    def validate_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        validate_password(value)
        return value

    def create(self, validated_data):
        from apps.accounts.models import AuthIdentity, Consent

        password = validated_data.pop("password")
        terms_version = validated_data.pop("terms_version", "2026-10")

        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            language=validated_data.get("language", "en"),
            password=password,
            status=User.Status.ACTIVE,
            email_verified=False,
        )

        AuthIdentity.objects.create(
            user=user,
            provider=AuthIdentity.Provider.PASSWORD,
            verified_at=timezone.now(),
        )

        Consent.objects.create(user=user, type=Consent.ConsentType.TERMS, version=terms_version)
        Consent.objects.create(user=user, type=Consent.ConsentType.PRIVACY, version=terms_version)

        return user


class EmailVerifySerializer(serializers.Serializer):
    """Verify an email address using the token from the verification email."""

    token = serializers.CharField()


class ResendVerificationSerializer(serializers.Serializer):
    """Request a new verification email."""

    email = serializers.EmailField()


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation of the current user."""

    class Meta:
        model = User
        fields = ["id", "email", "username", "language", "status", "email_verified", "created_at"]
        read_only_fields = fields


class TokenResponseSerializer(serializers.Serializer):
    """Shape of the token response after login."""

    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
