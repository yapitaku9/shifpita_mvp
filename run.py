import click
from app import create_app, db
from app.models.user import User
from app.models.master import ShiftType # Role
import datetime

app = create_app()


@app.cli.command("create-admin")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
def create_admin(username, password):
    """最初の管理者アカウントを作成します。"""
    if User.query.filter_by(is_admin=True).first():
        print("エラー: 管理者アカウントは既に存在します。")
        return

    # ユーザー名の要件チェック（半角英数字6文字以上）
    if not (username.isalnum() and len(username) >= 6):
        print("エラー: ユーザー名は半角英数字6文字以上で設定してください。")
        return

    # パスワード要件のチェック（半角数字4文字）
    if not (password.isdigit() and len(password) == 4):
        print("エラー: パスワードは半角数字4文字で設定してください。")
        return

    admin = User(username=username, is_admin=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"管理者 '{username}' が正常に作成されました。")


@app.cli.command("seed-data")
def seed_data():
    """役割とシフト種のマスターデータを投入します。"""
    print("Seeding master data...")

    # Roles
    # roles = [
    #     {"name": "介護員", "can_night_shift": True, "monthly_work_days_rule": 21},
    #     {"name": "パート1", "can_night_shift": True, "monthly_work_days_rule": None},
    #     {"name": "パート2", "can_night_shift": False, "monthly_work_days_rule": None},
    #     {"name": "パート3", "can_night_shift": False, "monthly_work_days_rule": None},
    #     {"name": "パート4", "can_night_shift": False, "monthly_work_days_rule": None},
    #     {"name": "責任者", "can_night_shift": True, "monthly_work_days_rule": None},
    #     {"name": "サポート", "can_night_shift": True, "monthly_work_days_rule": None},
    # ]
    # for r_data in roles:
    #     if not Role.query.filter_by(name=r_data['name']).first():
    #         role = Role(**r_data)
    #         db.session.add(role)
    #         print(f"  Added Role: {r_data['name']}")

    # ShiftTypes
    def t(h, m): return datetime.time(h, m)
    shift_types = [
        {"name": "早1", "start_time": t(7, 0), "end_time": t(16, 0)},
        {"name": "早2", "start_time": t(8, 0), "end_time": t(17, 0)},
        {"name": "日1", "start_time": t(10, 0), "end_time": t(19, 0)},
        {"name": "日2", "start_time": t(11, 0), "end_time": t(20, 0)},
        {"name": "遅1", "start_time": t(14, 0), "end_time": t(23, 0)},
        {"name": "遅2", "start_time": t(15, 0), "end_time": t(0, 0)},
        {"name": "夜1", "start_time": t(23, 0), "end_time": t(8, 0)},
        {"name": "夜2", "start_time": t(0, 0), "end_time": t(9, 0)},
        {"name": "明", "start_time": t(0, 0), "end_time": t(0, 0)},
        {"name": "休", "start_time": t(0, 0), "end_time": t(0, 0)},
        {"name": "1", "start_time": t(7, 0), "end_time": t(12, 0)},
        {"name": "2", "start_time": t(7, 0), "end_time": t(13, 0)},
        {"name": "3", "start_time": t(8, 0), "end_time": t(13, 0)},
        {"name": "4", "start_time": t(8, 0), "end_time": t(14, 0)},
        {"name": "5", "start_time": t(8, 30), "end_time": t(13, 30)},
        {"name": "6", "start_time": t(9, 0), "end_time": t(14, 0)},
        {"name": "7", "start_time": t(9, 0), "end_time": t(15, 0)},
        {"name": "8", "start_time": t(13, 0), "end_time": t(19, 0)},
    ]
    for s_data in shift_types:
        if not ShiftType.query.filter_by(name=s_data['name']).first():
            st = ShiftType(**s_data)
            db.session.add(st)
            print(f"  Added ShiftType: {s_data['name']}")
    
    db.session.commit()
    print("Master data seeding complete.")


if __name__ == "__main__":
    app.run(debug=True, port=8000)

