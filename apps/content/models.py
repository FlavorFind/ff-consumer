"""Content models — Taste of 47 Counties editorial stories."""

import uuid

from django.db import models
from django.utils.text import slugify


class Story(models.Model):
    """An editorial story about regional Kenyan food.

    Stories are written by the content team and linked to engine region slugs.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=200, unique=True)
    title_en = models.CharField(max_length=300)
    title_sw = models.CharField(max_length=300, blank=True, default="")
    body_en = models.TextField()
    body_sw = models.TextField(blank=True, default="")
    # Comma-separated engine region slugs this story covers
    region_slugs = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Comma-separated engine region slugs (e.g. 'mombasa,kilifi,lamu').",
    )
    author = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "story"
        verbose_name_plural = "stories"
        ordering = ["-published_at"]

    def __str__(self):
        return self.title_en

    def get_region_slug_list(self) -> list[str]:
        return [s.strip() for s in self.region_slugs.split(",") if s.strip()]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title_en)[:200]
        super().save(*args, **kwargs)
