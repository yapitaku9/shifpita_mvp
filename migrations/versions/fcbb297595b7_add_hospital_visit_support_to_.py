"""add hospital_visit_support to employmenttype enum

Revision ID: fcbb297595b7
Revises: 1dd67e116f37
Create Date: 2026-03-21 07:54:08.687968

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fcbb297595b7'
down_revision = '1dd67e116f37'
branch_labels = None
depends_on = None


def upgrade():
    # Add the new value to the existing 'employmenttype' ENUM in PostgreSQL.
    op.execute("ALTER TYPE employmenttype ADD VALUE 'HOSPITAL_VISIT_SUPPORT'")


def downgrade():
    # Removing a value from an ENUM is a complex operation that is not
    # easily reversible and can cause issues if the value is in use.
    # As a safe measure, this downgrade path does nothing. A manual
    # review would be needed to perform a true rollback.
    pass
