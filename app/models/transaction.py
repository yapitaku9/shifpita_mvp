import datetime
from peewee import IntegerField, DateTimeField, CharField, ForeignKeyField, DateField, AutoField
from app.models.base import BaseModel
from app.models.master import Role, ShiftType


class ShiftContext(BaseModel):
    """シフト作成コンテキスト"""

    context_id = AutoField()
    year = IntegerField()
    month = IntegerField()
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "shift_contexts"


class Employee(BaseModel):
    """従業員"""

    employee_id = AutoField()
    context = ForeignKeyField(ShiftContext, backref="employees", on_delete="CASCADE")
    role = ForeignKeyField(Role, backref="employees")
    name = CharField(max_length=100)

    class Meta:
        table_name = "employees"
        indexes = ((("context",), False),)  # idx_employee_context


class DayOffRequest(BaseModel):
    """希望休"""

    request_id = AutoField()
    employee = ForeignKeyField(Employee, backref="day_off_requests", on_delete="CASCADE")
    date = DateField()

    class Meta:
        table_name = "day_off_requests"
        indexes = ((("employee", "date"), True),)  # Unique constraint


class SpecialDay(BaseModel):
    """特別日"""

    special_day_id = AutoField()
    context = ForeignKeyField(ShiftContext, backref="special_days", on_delete="CASCADE")
    date = DateField()
    additional_staff_count = IntegerField(default=0)

    class Meta:
        table_name = "special_days"
        indexes = ((("context", "date"), True),)  # Unique constraint


class ShiftAssignment(BaseModel):
    """シフト割当結果"""

    assignment_id = AutoField()
    context = ForeignKeyField(ShiftContext, backref="assignments", on_delete="CASCADE")
    employee = ForeignKeyField(Employee, backref="assignments", on_delete="CASCADE")
    shift_type = ForeignKeyField(ShiftType, backref="assignments")
    date = DateField()

    class Meta:
        table_name = "shift_assignments"
        indexes = (
            (("employee", "date"), True),  # Unique constraint
            (("context",), False),  # idx_assignment_context
        )
