"""Profile models for ff-consumer."""

import uuid

from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Extended profile for a user — household, region, budget."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    household_size = models.PositiveIntegerField(default=1)
    region_slug = models.CharField(max_length=100, blank=True, default="")
    budget_kes_per_meal = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "profile"


class ProfileDiet(models.Model):
    """Diet tags and allergen exclusions — sent on every engine search call."""

    class Source(models.TextChoices):
        USER_SET = "user_set", "User Set"
        ALLERGEN = "allergen", "Allergen"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="diet_tags",
    )
    # Engine dietary tag slug, e.g. "vegetarian", "nut-free", "halal"
    diet_tag_slug = models.CharField(max_length=100, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.USER_SET)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "diet_tag_slug")]
        verbose_name = "profile diet tag"
        verbose_name_plural = "profile diet tags"
