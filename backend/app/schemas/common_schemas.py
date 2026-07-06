"""Common shared schemas for API responses."""

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """Generic success response wrapper."""
    success: bool
    message: str
    data: Any | None = None


class ErrorResponse(BaseModel):
    """Generic error response."""
    success: bool = False
    error: str
    detail: str | None = None


class TokenResponse(BaseModel):
    """JWT token response."""
    token: str


# ── Settings schemas ──────────────────────────────────────────────────────────


class SettingItem(BaseModel):
    """A single system setting as returned by the API."""
    key: str
    value: str
    description: str | None = None


class SettingsUpdateRequest(BaseModel):
    """Partial update of system settings: {key: value, ...}."""
    settings: dict[str, str]
