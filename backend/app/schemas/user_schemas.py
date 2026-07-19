"""User schemas with Israeli phone validation."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.constants import ShiftType, UserRole
from app.messages import Messages


def _validate_israeli_phone(phone: str) -> str:
    """Validate and normalize Israeli phone number to 972XXXXXXXXX format.

    Accepts formats:
    - 05XXXXXXXX (10 digits starting with 05)
    - +972XXXXXXXXX (+972 followed by 9 digits)
    - 972XXXXXXXXX (972 followed by 9 digits)
    - With spaces/dashes that get stripped

    Always returns in 972XXXXXXXXX format (no leading +).
    """
    # Strip spaces, dashes, and leading +
    cleaned = phone.replace(" ", "").replace("-", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    # Israeli local format: starts with 05, 10 digits total → normalize to 972
    if re.match(r"^05\d{8}$", cleaned):
        return "972" + cleaned[1:]

    # International format: 972 followed by 9 digits
    if re.match(r"^972\d{9}$", cleaned):
        return cleaned

    raise ValueError(Messages.VAL_INVALID_PHONE)


def _validate_preferred_shift(value: str | None) -> str | None:
    """Validate an optional preferred shift.

    Empty string is kept as-is: on update it means "clear the preference"
    (the service normalizes it to NULL; plain None means "field not sent"
    and is dropped by exclude_none).
    """
    if value is None or value == "":
        return value
    if value not in {s.value for s in ShiftType}:
        raise ValueError(Messages.VAL_INVALID_PREFERRED_SHIFT)
    return value


class UserCreate(BaseModel):
    """Schema for creating a new user."""
    phone_number: str
    first_name: str
    last_name: str
    roles: list[UserRole] = Field(default_factory=list)
    exemptions_notes: str | None = None
    min_total_shifts: int = 0
    min_night_shifts: int = 0
    min_evening_shifts: int = 0
    payroll_employee_id: str | None = None
    payroll_ylm_code: str | None = None
    preferred_shift: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_israeli_phone(v)

    @field_validator("preferred_shift")
    @classmethod
    def validate_preferred_shift(cls, v: str | None) -> str | None:
        return _validate_preferred_shift(v)


class UserUpdate(BaseModel):
    """Schema for updating a user — all fields optional."""
    phone_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    roles: list[UserRole] | None = None
    is_active: bool | None = None
    exemptions_notes: str | None = None
    min_total_shifts: int | None = None
    min_night_shifts: int | None = None
    min_evening_shifts: int | None = None
    payroll_employee_id: str | None = None
    payroll_ylm_code: str | None = None
    preferred_shift: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_israeli_phone(v)

    @field_validator("preferred_shift")
    @classmethod
    def validate_preferred_shift(cls, v: str | None) -> str | None:
        return _validate_preferred_shift(v)


class UserResponse(BaseModel):
    """Schema for user data in API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number: str
    first_name: str
    last_name: str
    full_name: str | None = None
    roles: list[UserRole] = Field(default_factory=list)
    is_active: bool
    telegram_id: str | None = None
    exemptions_notes: str | None = None
    min_total_shifts: int = 0
    min_night_shifts: int = 0
    min_evening_shifts: int = 0
    gps_consent_at: datetime | None = None
    payroll_employee_id: str | None = None
    payroll_ylm_code: str | None = None
    preferred_shift: str | None = None
    created_at: datetime


class UserListResponse(BaseModel):
    """Paginated list of users."""
    users: list[UserResponse]
    count: int


# ── Auth schemas ──────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Schema for login requests (telegram and admin)."""
    init_data: str | None = None
    username: str | None = None
    password: str | None = None


class ChangePasswordRequest(BaseModel):
    """Schema for admin self-service password change."""
    current_password: str
    new_password: str


# ── Admin management schemas (SUPER_ADMIN only) ───────────────────────────────


class AdminCreateRequest(BaseModel):
    """Create a new dashboard admin. Role is assignable (admin/viewer) —
    SUPER_ADMIN is never assignable (hierarchy model)."""
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    password: str
    role: str = "admin"


class AdminSetActiveRequest(BaseModel):
    """Activate/deactivate an admin account."""
    active: bool


class AdminChangeRoleRequest(BaseModel):
    """Change an admin's role (admin/viewer)."""
    role: str


class AdminResetPasswordRequest(BaseModel):
    """Set a new password for another admin."""
    new_password: str


class AdminResponse(BaseModel):
    """Admin account as exposed to the management UI — never the hash."""
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime | None = None


class AdminListResponse(BaseModel):
    admins: list[AdminResponse]
    count: int
