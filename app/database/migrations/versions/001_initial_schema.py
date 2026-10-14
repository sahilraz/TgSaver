"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-11 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure clean slate if tables already exist
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if 'archive_items' in existing_tables:
        op.drop_table('archive_items')
    if 'batch_jobs' in existing_tables:
        op.drop_table('batch_jobs')
    if 'archive_mappings' in existing_tables:
        op.drop_table('archive_mappings')
    if 'user_settings' in existing_tables:
        op.drop_table('user_settings')
    if 'auth_states' in existing_tables:
        op.drop_table('auth_states')
    if 'user_sessions' in existing_tables:
        op.drop_table('user_sessions')
    if 'users' in existing_tables:
        op.drop_table('users')

    op.create_table(
        'users',
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('first_name', sa.String(length=128), nullable=True),
        sa.Column('is_connected', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('telegram_id')
    )

    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=False)

    op.create_table(
        'user_sessions',
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('encrypted_session', sa.Text(), nullable=True),
        sa.Column('phone_number', sa.String(length=32), nullable=True),
        sa.Column('account_id', sa.BigInteger(), nullable=True),
        sa.Column('account_first_name', sa.String(length=128), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['telegram_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('telegram_id')
    )

    op.create_table(
        'auth_states',
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False),
        sa.Column('phone_number', sa.String(length=32), nullable=True),
        sa.Column('phone_code_hash', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['telegram_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('telegram_id')
    )

    op.create_table(
        'user_settings',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('is_paused', sa.Boolean(), nullable=False, default=False),
        sa.Column('prefer_copy', sa.Boolean(), nullable=False, default=True),
        sa.Column('auto_create_channels', sa.Boolean(), nullable=False, default=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id')
    )

    op.create_table(
        'archive_mappings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('source_channel_ref', sa.String(length=128), nullable=False),
        sa.Column('source_title', sa.String(length=256), nullable=True),
        sa.Column('destination_channel_id', sa.BigInteger(), nullable=False),
        sa.Column('destination_title', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source_channel_ref', name='uq_user_source_channel')
    )
    op.create_index(op.f('ix_archive_mappings_user_id'), 'archive_mappings', ['user_id'], unique=False)
    op.create_index(op.f('ix_archive_mappings_source_channel_ref'), 'archive_mappings', ['source_channel_ref'], unique=False)

    op.create_table(
        'batch_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('total_items', sa.Integer(), nullable=False),
        sa.Column('completed_items', sa.Integer(), nullable=False),
        sa.Column('failed_items', sa.Integer(), nullable=False),
        sa.Column('skipped_items', sa.Integer(), nullable=False),
        sa.Column('bytes_transferred', sa.BigInteger(), nullable=False),
        sa.Column('status_message_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_batch_jobs_user_id'), 'batch_jobs', ['user_id'], unique=False)
    op.create_index(op.f('ix_batch_jobs_status'), 'batch_jobs', ['status'], unique=False)

    op.create_table(
        'archive_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('batch_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('source_url', sa.String(length=512), nullable=False),
        sa.Column('source_channel_ref', sa.String(length=128), nullable=False),
        sa.Column('source_message_id', sa.Integer(), nullable=False),
        sa.Column('destination_channel_id', sa.BigInteger(), nullable=True),
        sa.Column('destination_message_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('method', sa.String(length=32), nullable=False),
        sa.Column('file_name', sa.String(length=256), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('error_category', sa.String(length=64), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['batch_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source_channel_ref', 'source_message_id', name='uq_user_source_message')
    )
    op.create_index(op.f('ix_archive_items_batch_id'), 'archive_items', ['batch_id'], unique=False)
    op.create_index(op.f('ix_archive_items_user_id'), 'archive_items', ['user_id'], unique=False)
    op.create_index(op.f('ix_archive_items_source_channel_ref'), 'archive_items', ['source_channel_ref'], unique=False)
    op.create_index(op.f('ix_archive_items_source_message_id'), 'archive_items', ['source_message_id'], unique=False)


def downgrade() -> None:
    op.drop_table('archive_items')
    op.drop_table('batch_jobs')
    op.drop_table('archive_mappings')
    op.drop_table('user_settings')
    op.drop_table('auth_states')
    op.drop_table('user_sessions')
    op.drop_table('users')
