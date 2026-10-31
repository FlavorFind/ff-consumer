"""Shared DRF permissions for ff-consumer."""

from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Object-level permission — only the owner of an object may access it.

    Views using this permission must call ``self.get_object()`` which triggers
    ``check_object_permissions``.
    """

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id
