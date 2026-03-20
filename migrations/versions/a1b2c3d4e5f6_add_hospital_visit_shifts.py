"""add_hospital_visit_shifts

Revision ID: a1b2c3d4e5f6
Revises: f67ae448a515
Create Date: 2026-03-20 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Time
import datetime


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f67ae448a515'
branch_labels = None
depends_on = None


def upgrade():
    # Define the table structure for the bulk insert
    shift_types_table = table('shift_types',
        column('name', String),
        column('start_time', Time),
        column('end_time', Time)
    )

    # Insert new shift types
    op.bulk_insert(shift_types_table,
        [
            {'name': '通8', 'start_time': datetime.time(8, 0), 'end_time': datetime.time(9, 0)},
            {'name': '通9', 'start_time': datetime.time(9, 0), 'end_time': datetime.time(10, 0)},
        ]
    )

def downgrade():
    # Delete the shift types added in the upgrade
    op.execute("DELETE FROM shift_types WHERE name IN ('通8', '通9')")
