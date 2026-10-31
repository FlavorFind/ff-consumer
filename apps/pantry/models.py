"""Pantry models — what a user has at home."""

import uuid

from django.conf import settings
from django.db import models


class PantryItem(models.Model):
    """An ingredient in the user's pantry.

    Stores the engine's ingredient ID and slug — not a copy of the ingredient.
    The display_name is cached from the engine and refreshed on dataset_version change.
    Quantities are NOT stored — the engine ignores them in v1.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pantry_items",
    )
    # Engine ingredient reference — not a FK (engine DB is separate)
    ingredient_id = models.CharField(max_length=36, db_index=True)  # engine UUID
    ingredient_slug = models.CharField(max_length=200, db_index=True)  # engine slug
    display_name = models.CharField(max_length=200)  # cached from engine
    added_at = models.DateTimeField(auto_now_add=True)
    expires_on = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "pantry item"
        verbose_name_plural = "pantry items"
        unique_together = [("user", "ingredient_id")]
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.user} — {self.display_name}"
