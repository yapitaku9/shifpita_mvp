<<<<<<< HEAD
from app.models.base import db, BaseModel
from app.models.master import Role, ShiftType
from app.models.user import User

# アプリケーションで使用するすべてのモデルをリストアップします。
# db.create_tables() がこれらのモデルのテーブルを作成するために使用します。
ALL_MODELS = [
    Role,
    ShiftType,
    User,  # 新しく追加されたUserモデル
]


def create_tables():
    """定義されたすべてのモデルのテーブルを作成します。"""
    db.create_tables(ALL_MODELS)
=======
# flake8: noqa
# This file imports the SQLAlchemy models to make them accessible,
# for example for Flask-Migrate and the Flask shell.

from .user import User
from .master import Role, ShiftType
from .day_off_request import DayOffRequest
from .shift import ShiftAssignment
from .history import ShiftGenerationHistory
from .special_day import SpecialDay
from .work_request import WorkRequest
>>>>>>> feature
