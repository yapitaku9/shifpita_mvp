from app.models.base import db
from app.models.master import Role, ShiftType, ConstraintRule
from app.models.transaction import ShiftContext, Employee, DayOffRequest, SpecialDay, ShiftAssignment


def create_tables():
    """定義されたモデルのテーブルを作成します。"""
    with db:
        db.create_tables(
            [
                Role,
                ShiftType,
                ConstraintRule,
                ShiftContext,
                Employee,
                DayOffRequest,
                SpecialDay,
                ShiftAssignment,
            ],
            safe=True,
        )
