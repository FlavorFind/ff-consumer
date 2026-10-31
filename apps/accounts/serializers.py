"""Serializers for the accounts app."""

import phonenumbers
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Add user language and plan to the JWT payload."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["language"] = user.language
        return token


class RegisterSerializer(serializers.Serializer):
    """Registration with email+password."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    language = serializers.ChoiceField(choices=["en", "sw"], default="en")
    terms_version = serializers.CharField(default="2026-10")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

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
            language=validated_data.get("language", "en"),
            password=password,
            status=User.Status.ACTIVE,
        )

        AuthIdentity.objects.create(
            user=user,
            provider=AuthIdentity.Provider.PASSWORD,
            verified_at=timezone.now(),
        )

        Consent.objects.create(user=user, type=Consent.ConsentType.TERMS, version=terms_version)
        Consent.objects.create(user=user, type=Consent.ConsentType.PRIVACY, version=terms_version)

        return user


class OTPRequestSerializer(serializers.Serializer):
    """Request a phone OTP."""

    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value):
        try:
            parsed = phonenumbers.parse(value, "KE")
            if not phonenumbers.is_valid_number(parsed):
                raise serializers.ValidationError("Invalid phone number.")
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException as exc:
            raise serializers.ValidationError("Invalid phone number format.") from exc


class OTPVerifySerializer(serializers.Serializer):
    """Verify a phone OTP and return JWT tokens."""

    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(min_length=6, max_length=6)

    def validate_phone(self, value):
        try:
            parsed = phonenumbers.parse(value, "KE")
            if not phonenumbers.is_valid_number(parsed):
                raise serializers.ValidationError("Invalid phone number.")
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException as exc:
            raise serializers.ValidationError("Invalid phone number format.") from exc


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation of the current user."""

    class Meta:
        model = User
        fields = ["id", "email", "phone", "language", "status", "created_at"]
        read_only_fields = fields


class TokenResponseSerializer(serializers.Serializer):
    """Shape of the token response after login."""

    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
