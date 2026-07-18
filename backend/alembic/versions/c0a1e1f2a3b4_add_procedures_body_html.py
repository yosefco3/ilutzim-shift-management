"""add procedures.body_html — sanitized HTML snapshot of the uploaded docx

Adds ``body_html`` (nullable TEXT) to ``procedures``. Populated at upload time
by ``extract_html_from_docx`` (mammoth → nh3-sanitized). NULL for procedures
created before this feature or pasted as plain text — the guard WebApp page
then falls back to rendering ``body_text``. The plain-text editor keeps editing
``body_text`` only; ``body_html`` is a frozen snapshot of the uploaded docx.

Ships dark behind PROCEDURES_ENABLED (default False).

Revision ID: c0a1e1f2a3b4
Revises: a6c8e0f2b4d6
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c0a1e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'a6c8e0f2b4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'procedures',
        sa.Column('body_html', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('procedures', 'body_html')
