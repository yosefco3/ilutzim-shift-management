"""
UserService — business logic for user (guard) management.
"""

import logging
import re
import uuid

from app.exceptions import UserDeactivatedException, UserNotFoundException
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user_schemas import UserCreate, UserResponse, UserUpdate

logger = logging.getLogger("ilutzim")


def _normalize_phone(phone: str) -> str:
    """Normalize phone to 972XXXXXXXXX format (must match DB storage)."""
    original = phone
    cleaned = phone.replace(" ", "").replace("-", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    # Local format 05XXXXXXXX → 972XXXXXXXXX
    if re.match(r"^05\d{8}$", cleaned):
        result = "972" + cleaned[1:]
        logger.debug("Phone normalized: %r → %r", original, result)
        return result
    # Already international
    if re.match(r"^972\d{9}$", cleaned):
        logger.debug("Phone already international: %r", cleaned)
        return cleaned
    logger.warning("Phone format unexpected: %r → %r (returning as-is)", original, cleaned)
    return cleaned  # Return as-is for edge cases


class UserService:
    """Orchestrates user CRUD with business rules."""

    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    async def create_user(self, data: UserCreate) -> UserResponse:
        """Create a new guard and return the response."""
        logger.info(
            "Creating user: phone=%s, first_name=%s, last_name=%s",
            data.phone_number, data.first_name, data.last_name,
        )
        user = User(
            phone_number=data.phone_number,
            first_name=data.first_name,
            last_name=data.last_name,
            roles=[r.value for r in data.roles],
            min_total_shifts=data.min_total_shifts,
            min_night_shifts=data.min_night_shifts,
            min_evening_shifts=data.min_evening_shifts,
            exemptions_notes=data.exemptions_notes,
            payroll_employee_id=data.payroll_employee_id or None,
            payroll_ylm_code=data.payroll_ylm_code or None,
            preferred_shift=data.preferred_shift or None,
        )
        created = await self._user_repo.save(user)
        logger.info("User created successfully: id=%s, phone=%s", created.id, created.phone_number)

        # ── Try to send welcome notification via Telegram ──
        await self._try_send_welcome_notification(created)

        return UserResponse.model_validate(created)

    async def _try_send_welcome_notification(self, user: User) -> None:
        """Attempt to send a welcome notification to a newly created guard.

        For new users without telegram_id, the notification will be sent
        later when they verify their phone through the bot (/start flow).
        """
        try:
            from app.bot.notifications import notify_guard_welcome
            from app.bot.bot_instance import get_bot

            # Check if bot is available
            try:
                bot = get_bot()
                if bot is None:
                    logger.warning(
                        "Telegram bot not available — cannot send welcome notification "
                        "to user %s (phone=%s)",
                        user.id, user.phone_number,
                    )
                    return
            except Exception as bot_exc:
                logger.warning(
                    "Telegram bot not initialized — cannot send welcome notification: %s", bot_exc
                )
                return

            if user.telegram_id:
                # User already has a telegram_id linked — send welcome directly
                tg_id = int(user.telegram_id)
                logger.info(
                    "Sending welcome notification to existing telegram user: "
                    "user_id=%s, telegram_id=%s", user.id, tg_id,
                )
                success = await notify_guard_welcome(
                    tg_id, user.first_name or "", user.last_name or "",
                )
                if success:
                    logger.info("Welcome notification sent successfully to telegram_id=%s", tg_id)
                else:
                    logger.warning("Welcome notification failed for telegram_id=%s", tg_id)
            else:
                logger.info(
                    "No telegram_id for user %s (phone=%s). "
                    "Welcome notification will be sent when the guard starts the bot "
                    "and verifies their phone number.",
                    user.id, user.phone_number,
                )
        except Exception as exc:
            logger.error("Error in welcome notification attempt for user %s: %s", user.id, exc)

    async def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> UserResponse:
        """Update an existing guard's details."""
        user = await self._get_user_or_raise(user_id)
        update_data = data.model_dump(exclude_none=True)
        if "roles" in update_data:
            # Store plain string values in the JSON column, not enum members.
            update_data["roles"] = [r.value for r in data.roles]
        if "preferred_shift" in update_data:
            # Empty string from the form means "clear the preference".
            update_data["preferred_shift"] = update_data["preferred_shift"] or None
        for field, value in update_data.items():
            setattr(user, field, value)
        updated = await self._user_repo.save(user)
        logger.info(f"User updated: id={user_id}")
        return UserResponse.model_validate(updated)

    async def deactivate_user(self, user_id: uuid.UUID) -> UserResponse:
        """Set is_active=False for a guard."""
        user = await self._get_user_or_raise(user_id)
        user.is_active = False
        updated = await self._user_repo.save(user)
        logger.info(f"User deactivated: id={user_id}")
        return UserResponse.model_validate(updated)

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        """Permanently delete a guard from the database."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            return False
        await self._user_repo.delete(user_id)
        logger.info(f"User permanently deleted: id={user_id}, phone={user.phone_number}")
        return True

    async def get_all_active_users(self) -> list[UserResponse]:
        """Return all active users."""
        users = await self._user_repo.get_active_users()
        return [UserResponse.model_validate(u) for u in users]

    async def get_all_users(self) -> list[UserResponse]:
        """Return all users (active and inactive) — used by admin."""
        users = await self._user_repo.get_all_users()
        return [UserResponse.model_validate(u) for u in users]

    async def get_user(self, user_id: uuid.UUID) -> UserResponse:
        """Get a single guard by ID."""
        user = await self._get_user_or_raise(user_id)
        return UserResponse.model_validate(user)

    # ── Telegram / Bot methods ─────────────────────────────────────────

    async def get_by_telegram_id(self, telegram_id: int) -> UserResponse | None:
        """Find a user by Telegram ID. Returns None if not found."""
        user = await self._user_repo.get_by_telegram_id(str(telegram_id))
        if user is None:
            return None
        return UserResponse.model_validate(user)

    async def link_telegram(self, phone_number: str, telegram_id: str) -> UserResponse:
        """Bot authentication: find user by phone and link telegram_id."""
        phone_number = _normalize_phone(phone_number)
        logger.info("Linking telegram: phone=%s, telegram_id=%s", phone_number, telegram_id)
        user = await self._user_repo.get_by_phone(phone_number)
        if user is None:
            logger.warning("Telegram link failed — phone not found: %s", phone_number)
            raise UserNotFoundException()
        if not user.is_active:
            logger.warning("Telegram link failed — user deactivated: phone=%s", phone_number)
            raise UserDeactivatedException()
        user = await self._user_repo.link_telegram_id_by_phone(phone_number, telegram_id)
        logger.info("Telegram linked successfully: user_id=%s, telegram_id=%s", user.id, telegram_id)
        return UserResponse.model_validate(user)

    async def link_telegram_by_user_id(self, user_id: uuid.UUID, telegram_id: str) -> UserResponse:
        """Link telegram_id to a user by their user ID."""
        user = await self._get_user_or_raise(user_id)
        if not user.is_active:
            raise UserDeactivatedException()
        user = await self._user_repo.link_telegram_id_by_user_id(user_id, telegram_id)
        logger.info(f"Telegram linked by user_id: user_id={user_id}, telegram_id={telegram_id}")
        return UserResponse.model_validate(user)

    async def get_user_by_phone(self, phone_number: str) -> UserResponse | None:
        """Find user by phone number. Returns None if not found."""
        phone_number = _normalize_phone(phone_number)
        user = await self._user_repo.get_by_phone(phone_number)
        if user is None:
            return None
        return UserResponse.model_validate(user)

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _get_user_or_raise(self, user_id: uuid.UUID) -> User:
        """Fetch user or raise UserNotFoundException."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundException()
        return user