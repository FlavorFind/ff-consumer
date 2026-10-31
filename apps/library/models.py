"""Library models — saved recipes, collections, cooking history."""

import uuid

from django.conf import settings
from django.db import models


class Collection(models.Model):
    """A named folder of saved recipes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="collections"
    )
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "name")]
        ordering = ["name"]

    def __str__(self):
        return f"{self.user} — {self.name}"


class SavedRecipe(models.Model):
    """A reference to an engine dish saved by a user.

    Stores the engine dish ID and slug — not a copy of the recipe.
    dataset_version is stored so drift can be detected by the nightly check.
    Free tier: max 20 saved recipes. Plus: unlimited.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_recipes"
    )
    dish_id = models.CharField(max_length=36, db_index=True)      # engine UUID
    dish_slug = models.CharField(max_length=200)                   # engine slug
    dataset_version = models.CharField(max_length=20)              # for drift detection
    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, null=True, blank=True, related_name="recipes"
    )
    note = models.TextField(blank=True, default="")
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "dish_id")]
        ordering = ["-saved_at"]

    def __str__(self):
        return f"{self.user} — {self.dish_slug}"


class CookLog(models.Model):
    """Records when a user cooked a dish."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cook_logs"
    )
    dish_id = models.CharField(max_length=36, db_index=True)
    dish_slug = models.CharField(max_length=200)
    cooked_at = models.DateTimeField(auto_now_add=True)
    rating = models.IntegerField(null=True, blank=True)  # 1–5
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-cooked_at"]

    def __str__(self):
        return f"{self.user} cooked {self.dish_slug} at {self.cooked_at}"
