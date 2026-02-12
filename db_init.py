from app import create_app
from app.models.base import db
from app.models.user import User
from app.models.master import Role, ShiftType, ConstraintRule
from app.models.employee import Employee


def init_db(app):
    """データベースを初期化し、テーブルを作成します。"""
    with app.app_context():
        print("データベーステーブルを作成します...")
        db.connect()
        db.create_tables(
            [
                User,
                Role,
                ShiftType,
                ConstraintRule,
                Employee,
            ]
        )
        db.close()
        print("データベーステーブルの作成が完了しました。")


if __name__ == "__main__":
    app = create_app()
    init_db(app)
