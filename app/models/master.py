from peewee import CharField, BooleanField, IntegerField, TimeField, AutoField
from playhouse.sqlite_ext import JSONField
from app.models.base import BaseModel


class Role(BaseModel):
    """役割マスタ"""

    role_id = AutoField()
    name = CharField(unique=True, max_length=50)
    can_night_shift = BooleanField(default=False)
    monthly_work_days_rule = IntegerField(null=True)

    class Meta:
        table_name = "roles"


class ShiftType(BaseModel):
    """シフト区分マスタ"""

    shift_type_id = AutoField()
    name = CharField(unique=True, max_length=20)
    start_time = TimeField()
    end_time = TimeField()

    class Meta:
        table_name = "shift_types"


class ConstraintRule(BaseModel):
    """制約ルールマスタ"""

    rule_id = AutoField()
    type = CharField(max_length=20)  # 'HARD' or 'SOFT'
    parameters = JSONField()  # playhouse.sqlite_ext.JSONField

    class Meta:
        table_name = "constraint_rules"
