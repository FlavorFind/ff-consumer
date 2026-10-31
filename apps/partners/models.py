"""Partners models — sponsored slots.

Sponsored content is ALWAYS labelled to users ("Sponsored" label in API response).
Never hide the sponsored nature of a result.
"""

import uuid

from django.db import models


class SponsoredSlot(models.Model):
    """A sponsored dish or ingredient slot.

    Partner pays to have a dish or ingredient promoted in search results
    or on ingredient pages. Must be labelled "Sponsored" in every response.

    sponsored_type:
      - "dish"       → dish_id is an engine dish UUID
      - "ingredient" → dish_id is an engine ingredient UUID
    """

    class SponsoredType(models.TextChoices):
        DISH = "dish", "Dish"
        INGREDIENT = "ingredient", "Ingredient"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner_name = models.CharField(max_length=200)
    sponsored_type = models.CharField(
        max_length=20, choices=SponsoredType.choices, default=SponsoredType.DISH
    )
    # Engine UUID for the promoted item — not a FK (lives in engine DB)
    engine_id = models.CharField(max_length=36, db_index=True)
    engine_slug = models.CharField(max_length=200)
    display_name = models.CharField(max_length=300)
    label = models.CharField(
        max_length=50,
        default="Sponsored",
        help_text="Label shown to users — must not be misleading.",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "sponsored slot"
        verbose_name_plural = "sponsored slots"

    def __str__(self):
        return f"{self.partner_name} — {self.display_name} ({self.sponsored_type})"
