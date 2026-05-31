"""add booking with gist exclude constraint

Revision ID: c1d4e7a92b58
Revises: 8a2f1c4b9e30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d4e7a92b58'
down_revision: Union[str, None] = '8a2f1c4b9e30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        'booking',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('resource_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('starts_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('ends_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resource_id'], ['resource.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['user_account.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('ends_at > starts_at', name='ck_booking_positive_duration'),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled')",
            name='ck_booking_status',
        ),
    )
    op.create_index('ix_booking_organization_id', 'booking', ['organization_id'])
    op.create_index('ix_booking_user_id', 'booking', ['user_id'])

    op.execute("""
        ALTER TABLE booking ADD CONSTRAINT booking_no_overlap
        EXCLUDE USING gist (
            resource_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        ) WHERE (status IN ('pending', 'confirmed'))
    """)


def downgrade() -> None:
    op.drop_index('ix_booking_user_id', table_name='booking')
    op.drop_index('ix_booking_organization_id', table_name='booking')
    op.drop_table('booking')
