"""update late/night shift times and add 遅3 夜3 通10

Revision ID: e7c1a2b3d4f5
Revises: 884dd81ba563
Create Date: 2026-06-06 21:00:00.000000

顧客要望によるシフトマスターの変更:
- 遅1: 14:00-23:00 -> 13:00-22:00
- 遅2: 15:00-24:00 -> 14:00-23:00
- 遅3(新規): 15:00-24:00
- 夜1: 23:00-08:00 -> 22:00-07:00
- 夜2: 00:00-09:00 -> 23:00-08:00
- 夜3(新規): 00:00-09:00
- 通10(新規): 10:00-11:00

既存DB(本番)向けに、既存シフトの時刻を更新し、新規シフトを冪等に追加する。
新規DBでは作業シフトは flask seed が投入するため、ここでの UPDATE は0件でも問題ない
（その場合 seed が新しい時刻で投入する）。
"""
from alembic import op
import sqlalchemy as sa
import datetime


# revision identifiers, used by Alembic.
revision = 'e7c1a2b3d4f5'
down_revision = '884dd81ba563'
branch_labels = None
depends_on = None


# (name, start_time, end_time)
_UPDATED_TIMES = [
    ('遅1', datetime.time(13, 0), datetime.time(22, 0)),
    ('遅2', datetime.time(14, 0), datetime.time(23, 0)),
    ('夜1', datetime.time(22, 0), datetime.time(7, 0)),
    ('夜2', datetime.time(23, 0), datetime.time(8, 0)),
]

_NEW_SHIFTS = [
    {'name': '遅3', 'start_time': datetime.time(15, 0), 'end_time': datetime.time(0, 0)},
    {'name': '夜3', 'start_time': datetime.time(0, 0), 'end_time': datetime.time(9, 0)},
    {'name': '通10', 'start_time': datetime.time(10, 0), 'end_time': datetime.time(11, 0)},
]

# 旧時刻（ダウングレード用）
_OLD_TIMES = [
    ('遅1', datetime.time(14, 0), datetime.time(23, 0)),
    ('遅2', datetime.time(15, 0), datetime.time(0, 0)),
    ('夜1', datetime.time(23, 0), datetime.time(8, 0)),
    ('夜2', datetime.time(0, 0), datetime.time(9, 0)),
]


def _shift_types_table():
    # 型付きテーブルを使うことで、SQLAlchemyのTime型アダプタが
    # SQLite/PostgreSQL双方で datetime.time を正しくバインドする。
    return sa.table(
        'shift_types',
        sa.column('name', sa.String),
        sa.column('start_time', sa.Time),
        sa.column('end_time', sa.Time),
    )


def _apply_times(times):
    conn = op.get_bind()
    t = _shift_types_table()
    for name, start_t, end_t in times:
        conn.execute(
            t.update().where(t.c.name == name).values(
                start_time=start_t, end_time=end_t
            )
        )


def upgrade():
    # 1. 既存シフトの時刻を更新（存在しない場合は0件更新で無害）
    _apply_times(_UPDATED_TIMES)

    # 2. 新規シフトを冪等に追加（既存DB向け。新規DBでは seed と二重にならないよう存在チェック）
    shift_types_table = _shift_types_table()
    conn = op.get_bind()
    new_names = [s['name'] for s in _NEW_SHIFTS]
    existing = {
        row[0]
        for row in conn.execute(
            sa.select(shift_types_table.c.name).where(
                shift_types_table.c.name.in_(new_names)
            )
        ).fetchall()
    }
    to_insert = [s for s in _NEW_SHIFTS if s['name'] not in existing]
    if to_insert:
        op.bulk_insert(shift_types_table, to_insert)


def downgrade():
    # 新規シフトを削除し、時刻を旧値に戻す
    op.execute("DELETE FROM shift_types WHERE name IN ('遅3', '夜3', '通10')")
    _apply_times(_OLD_TIMES)
