"""Multi-user isolation and ownership verification."""

from typing import Optional


class SecurityAuthorizationError(Exception):
    """Raised when an unauthorized user attempts to access another user's resource."""
    pass


def verify_user_ownership(resource_user_id: int, requesting_user_id: int, resource_name: str = "resource") -> None:
    """Strictly ensures the requesting Telegram user owns the targeted resource."""
    if resource_user_id != requesting_user_id:
        raise SecurityAuthorizationError(
            f"Unauthorized access: user {requesting_user_id} does not own {resource_name} belonging to {resource_user_id}"
        )
