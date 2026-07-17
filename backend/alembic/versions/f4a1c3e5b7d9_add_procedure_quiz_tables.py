"""add procedure_quiz tables (סד"פ — AI-generated quiz bank per procedure)

Five tables for the procedure-quiz feature:
  - procedures            — the security procedure (title/body/status lifecycle)
  - quiz_questions        — MCQ bank (AI-generated + manual), per procedure
  - quiz_attempts         — a guard's scored run (sampled subset, frozen answers)
  - quiz_poll_links       — maps a Telegram quiz poll id → attempt/question
  - procedure_reminders_sent — one-reminder-per-guard ledger

Ships dark behind PROCEDURES_ENABLED (default False); the tables existing does
not activate anything.

Revision ID: f4a1c3e5b7d9
Revises: 7b3c0c23e716
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f4a1c3e5b7d9'
down_revision: Union[str, Sequence[str], None] = '7b3c0c23e716'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'procedures',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=True),
        sa.Column(
            'status',
            sa.Enum('DRAFT', 'PUBLISHED', 'ARCHIVED', name='procedure_status'),
            nullable=False,
        ),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'quiz_questions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('procedure_id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('options', sa.JSON(), nullable=False),
        sa.Column('correct_index', sa.Integer(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column(
            'source',
            sa.Enum('AI', 'MANUAL', name='question_source'),
            nullable=False,
        ),
        sa.Column('edited_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['procedure_id'], ['procedures.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_quiz_questions_procedure',
        'quiz_questions',
        ['procedure_id'],
    )

    op.create_table(
        'quiz_attempts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('procedure_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('question_ids', sa.JSON(), nullable=False),
        sa.Column('answers', sa.JSON(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('correct_count', sa.Integer(), nullable=True),
        sa.Column('total_count', sa.Integer(), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'IN_PROGRESS', 'FINISHED', 'ABANDONED', name='quiz_attempt_status'
            ),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['procedure_id'], ['procedures.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_quiz_attempt_user_procedure',
        'quiz_attempts',
        ['user_id', 'procedure_id'],
    )
    # Partial unique index: at most one IN_PROGRESS attempt per
    # (user, procedure) — the double-"start quiz" race backstop. Emitted for
    # both PostgreSQL (prod) and SQLite (tests).
    op.create_index(
        'uq_quiz_attempt_one_in_progress',
        'quiz_attempts',
        ['user_id', 'procedure_id'],
        unique=True,
        postgresql_where=sa.text("status = 'IN_PROGRESS'"),
        sqlite_where=sa.text("status = 'IN_PROGRESS'"),
    )

    op.create_table(
        'quiz_poll_links',
        sa.Column('telegram_poll_id', sa.String(length=64), nullable=False),
        sa.Column('attempt_id', sa.Uuid(), nullable=False),
        sa.Column('question_id', sa.Uuid(), nullable=False),
        sa.Column('option_order', sa.JSON(), nullable=False),
        sa.Column('correct_option_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['attempt_id'], ['quiz_attempts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['quiz_questions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('telegram_poll_id'),
    )

    op.create_table(
        'procedure_reminders_sent',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('procedure_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['procedure_id'], ['procedures.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('procedure_id', 'user_id', name='uq_procedure_reminder_once'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('procedure_reminders_sent')
    op.drop_table('quiz_poll_links')
    op.drop_index('uq_quiz_attempt_one_in_progress', table_name='quiz_attempts')
    op.drop_index('ix_quiz_attempt_user_procedure', table_name='quiz_attempts')
    op.drop_table('quiz_attempts')
    op.drop_index('ix_quiz_questions_procedure', table_name='quiz_questions')
    op.drop_table('quiz_questions')
    op.drop_table('procedures')
    sa.Enum(name='quiz_attempt_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='question_source').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='procedure_status').drop(op.get_bind(), checkfirst=True)
