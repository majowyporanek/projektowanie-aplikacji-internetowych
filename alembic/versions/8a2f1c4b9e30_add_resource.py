"""add resource

Revision ID: 8a2f1c4b9e30
Revises: 0e76f214f275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8a2f1c4b9e30'
down_revision: Union[str, None] = '0e76f214f275'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'resource',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_resource_organization_id', 'resource', ['organization_id'])


def downgrade() -> None:
    op.drop_index('ix_resource_organization_id', table_name='resource')
    op.drop_table('resource')
