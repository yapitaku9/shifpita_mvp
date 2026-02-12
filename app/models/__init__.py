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
