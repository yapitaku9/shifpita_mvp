from peewee import CharField, ForeignKeyField, AutoField
from app.models.base import BaseModel
from app.models.master import Role
# context_id is a concept that is not yet implemented, so I will comment it out for now.
# from app.models.context import ShiftContext


class Employee(BaseModel):
    """従業員"""

    employee_id = AutoField()
    # context = ForeignKeyField(ShiftContext, backref="employees")
    role = ForeignKeyField(Role, backref="employees")
    name = CharField(max_length=100)

    class Meta:
        table_name = "employees"


class EmployeeSkill(BaseModel):
    """従業員の保有スキル"""

    employee = ForeignKeyField(Employee, backref="skills")
    # The Skill model is not yet defined, so I will comment this out.
    # skill = ForeignKeyField(Skill, backref="employees")

    class Meta:
        table_name = "employee_skills"
        primary_key = False
