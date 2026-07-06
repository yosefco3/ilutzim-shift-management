"""add user payroll fields (stage 3 — YLM report headers)

payroll_employee_id (מ.עובד) + payroll_ylm_code (קוד י.ל.מ), editable in the
guard form; national_id (ת.ז.) is PREPARED ONLY — column without UI (decision
4/7): the report prints it when present, blank otherwise.

Revision ID: f3a5c7e9d1b4
Revises: e1f3a5c7b9d2
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a5c7e9d1b4'
down_revision: Union[str, Sequence[str], None] = 'e1f3a5c7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('payroll_employee_id', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('payroll_ylm_code', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('national_id', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'national_id')
    op.drop_column('users', 'payroll_ylm_code')
    op.drop_column('users', 'payroll_employee_id')
