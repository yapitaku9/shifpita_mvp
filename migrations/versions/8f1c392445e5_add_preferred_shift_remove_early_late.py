"""add_preferred_shift_remove_early_late

Revision ID: 8f1c392445e5
Revises: dfc57f28c169
Create Date: 2026-02-22 10:57:09.051308

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f1c392445e5'
down_revision = 'dfc57f28c169'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preferred_shift_1_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('preferred_shift_2_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_users_preferred_shift_1_id_shift_types',
            'shift_types', ['preferred_shift_1_id'], ['shift_type_id']
        )
        batch_op.create_foreign_key(
            'fk_users_preferred_shift_2_id_shift_types',
            'shift_types', ['preferred_shift_2_id'], ['shift_type_id']
        )
        batch_op.drop_column('preferred_early_shifts')
        batch_op.drop_column('preferred_late_shifts')


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preferred_late_shifts', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('preferred_early_shifts', sa.Integer(), nullable=True))
        batch_op.drop_constraint('fk_users_preferred_shift_2_id_shift_types', type_='foreignkey')
        batch_op.drop_constraint('fk_users_preferred_shift_1_id_shift_types', type_='foreignkey')
        batch_op.drop_column('preferred_shift_2_id')
        batch_op.drop_column('preferred_shift_1_id')
