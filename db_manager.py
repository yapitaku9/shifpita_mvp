import datetime
from peewee import IntegrityError
from app import create_app
from app.models.base import db
from app.models import create_tables
from app.models.master import Role, ShiftType

app = create_app()


def init_db():
    """テーブルを作成し、初期データを投入します。"""
    print("Initializing database...")

    # データベース接続
    if db.is_closed():
        db.connect()

    # テーブル作成
    create_tables()
    print("Tables created.")

    # マスタデータ投入
    seed_roles()
    seed_shift_types()

    # 接続終了
    if not db.is_closed():
        db.close()

    print("Database initialization complete.")


def seed_roles():
    """役割マスタの初期データを投入します。"""
    roles = [
        {"name": "介護員", "can_night_shift": True, "monthly_work_days_rule": 21},
        {"name": "パート1", "can_night_shift": True, "monthly_work_days_rule": None},
        {"name": "パート2", "can_night_shift": False, "monthly_work_days_rule": None},
        {"name": "パート3", "can_night_shift": False, "monthly_work_days_rule": None},
        {"name": "パート4", "can_night_shift": False, "monthly_work_days_rule": None},
        {"name": "責任者", "can_night_shift": True, "monthly_work_days_rule": None},
        {"name": "サポート", "can_night_shift": True, "monthly_work_days_rule": None},
    ]

    print("Seeding Roles...")
    for data in roles:
        try:
            Role.create(**data)
            print(f"  Created Role: {data['name']}")
        except IntegrityError:
            print(f"  Role already exists: {data['name']}")


def seed_shift_types():
    """シフト区分マスタの初期データを投入します。"""

    def t(hour, minute):
        return datetime.time(hour, minute)

    shift_types = [
        {"name": "早1", "start_time": t(7, 0), "end_time": t(16, 0)},
        {"name": "早2", "start_time": t(7, 30), "end_time": t(16, 30)},
        {"name": "日1", "start_time": t(9, 0), "end_time": t(18, 0)},
        {"name": "日2", "start_time": t(9, 30), "end_time": t(18, 30)},
        {"name": "遅1", "start_time": t(11, 0), "end_time": t(20, 0)},
        {"name": "遅2", "start_time": t(11, 30), "end_time": t(20, 30)},
        {"name": "夜1", "start_time": t(16, 0), "end_time": t(10, 0)},
        {"name": "夜2", "start_time": t(17, 0), "end_time": t(11, 0)},
        {"name": "明", "start_time": t(0, 0), "end_time": t(0, 0)},
        {"name": "休", "start_time": t(0, 0), "end_time": t(0, 0)},
        {"name": "1", "start_time": t(8, 0), "end_time": t(12, 0)},
        {"name": "2", "start_time": t(9, 0), "end_time": t(13, 0)},
        {"name": "3", "start_time": t(10, 0), "end_time": t(14, 0)},
        {"name": "4", "start_time": t(11, 0), "end_time": t(15, 0)},
        {"name": "5", "start_time": t(12, 0), "end_time": t(16, 0)},
        {"name": "6", "start_time": t(13, 0), "end_time": t(17, 0)},
        {"name": "7", "start_time": t(14, 0), "end_time": t(18, 0)},
        {"name": "8", "start_time": t(15, 0), "end_time": t(19, 0)},
    ]

    print("Seeding ShiftTypes...")
    for data in shift_types:
        try:
            ShiftType.create(**data)
            print(f"  Created ShiftType: {data['name']}")
        except IntegrityError:
            print(f"  ShiftType already exists: {data['name']}")


if __name__ == "__main__":
    with app.app_context():
        init_db()
