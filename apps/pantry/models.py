"""Pantry models — what a user has at home."""

import uuid

from django.conf import settings
from django.db import models


UNIT_CHOICES = [
    ("pieces", "Pieces"),
    ("kg", "Kilograms"),
    ("g", "Grams"),
    ("l", "Litres"),
    ("ml", "Millilitres"),
    ("cups", "Cups"),
    ("tbsp", "Tablespoons"),
    ("tsp", "Teaspoons"),
    ("bunches", "Bunches"),
    ("packets", "Packets"),
    ("cans", "Cans"),
    ("bottles", "Bottles"),
]


class PantryItem(models.Model):
    """An ingredient in the user's pantry.

    Stores the engine's ingredient ID and slug — not a copy of the ingredient.
    The display_name is cached from the engine and refreshed on dataset_version change.

    quantity / unit: optional tracking of how much the user has.
    low_stock_threshold: when quantity drops to or below this value, a notification is queued.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pantry_items",
    )
    # Engine ingredient reference — not a FK (engine DB is separate)
    ingredient_id = models.CharField(max_length=36, db_index=True)   # engine UUID
    ingredient_slug = models.CharField(max_length=200, db_index=True) # engine slug
    display_name = models.CharField(max_length=200)                   # cached from engine

    # Optional quantity tracking
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="How much the user currently has. Null means 'unknown'.",
    )
    unit = models.CharField(
        max_length=20, blank=True, default="",
        choices=UNIT_CHOICES,
        help_text="Unit for quantity. Empty string when quantity is null/unknown.",
    )
    # Low-stock alert threshold — alert fires when quantity drops to ≤ this value
    low_stock_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=(
            "Send a low-stock notification when quantity drops to this level. "
            "Null = no alert."
        ),
    )

    added_at = models.DateTimeField(auto_now_add=True)
    expires_on = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "pantry item"
        verbose_name_plural = "pantry items"
        unique_together = [("user", "ingredient_id")]
        ordering = ["-added_at"]

    def __str__(self):
        qty_str = f" ({self.quantity} {self.unit})" if self.quantity is not None else ""
        return f"{self.user} — {self.display_name}{qty_str}"

    @property
    def is_low_stock(self) -> bool:
        """True when quantity is tracked and at or below the threshold."""
        if self.quantity is None or self.low_stock_threshold is None:
            return False
        return self.quantity <= self.low_stock_threshold
