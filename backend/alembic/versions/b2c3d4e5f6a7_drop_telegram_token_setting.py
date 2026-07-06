"""drop telegram_bot_token from system_settings

The Telegram bot token is now sourced exclusively from the TELEGRAM_BOT_TOKEN
environment variable. Remove any value previously stored via the (removed) admin
UI so no secret lingers in the database.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the telegram_bot_token row (token is env-only now)."""
    op.execute("DELETE FROM system_settings WHERE setting_key = 'telegram_bot_token'")


def downgrade() -> None:
    """No-op — we never restore a secret into the database."""
    pass
