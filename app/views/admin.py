from flask import render_template, flash, redirect, url_for, Blueprint, request, current_app
from flask_login import login_required, current_user
from app import db
from app.forms import EmployeeForm
from app.models.user import User
from app.services.generator import ShiftGenerator
from app.email import send_email
import datetime

# URLプレフィックス '/admin' を持つブループリントを作成
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def before_request():
    """
    ブループリント内の全ルートで実行される共通処理。
    管理者ユーザーでなければアクセスを拒否する。
    """
    if not current_user.is_admin:
        flash("このページにアクセスするには管理者権限が必要です。")
        return redirect(url_for("main.index"))


@admin_bp.route("/users", methods=["GET", "POST"])
def manage_users():
    """従業員の一覧表示と追加処理"""
    form = EmployeeForm()
    if form.validate_on_submit():
        # POSTリクエスト（従業員追加）の場合
        try:
            user = User(username=form.username.data, email=form.email.data or None, role_id=form.role.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f"従業員「{user.username}」を追加しました。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")
        return redirect(url_for("admin.manage_users"))

    # GETリクエストの場合
    # フォームのエラーをflashメッセージで表示
    if request.method == "POST":  # validate_on_submitがFalseだった場合
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")

    user_list = User.query.filter_by(is_admin=False).order_by(User.username).all()
    return render_template("admin/users.html", title="従業員管理", form=form, users=user_list)


@admin_bp.route("/generate", methods=["POST"])
def generate_shifts():
    """シフト生成を実行する"""
    year = request.form.get("year", type=int)
    month = request.form.get("month", type=int)

    if not year or not month:
        flash("年と月を指定してください。", "danger")
        return redirect(url_for("main.index"))

    flash(f"{year}年{month}月のシフト生成を開始します...", "info")

    try:
        # TODO: 本来は非同期処理にすべき（時間がかかるため）
        generator = ShiftGenerator()
        success = generator.run(year, month)

        if success:
            flash(f"{year}年{month}月のシフトが正常に作成・保存されました。", "success")
            # メールアドレスが登録されている全従業員に通知
            users_with_email = User.query.filter(User.email.isnot(None), User.is_admin == False).all()
            recipients = [user.email for user in users_with_email]
            if recipients:
                send_email(
                    subject=f"[シフぴた] {year}年{month}月分のシフトが作成されました",
                    recipients=recipients,
                    template="shift_generated",
                    year=year,
                    month=month,
                )
                flash(f"{len(recipients)}名の従業員に通知メールを送信しました。", "info")

        else:
            flash("シフトの作成に失敗しました。制約条件を見直してください。", "danger")

    except Exception as e:
        flash(f"シフト生成中に予期せぬエラーが発生しました: {e}", "danger")

    return redirect(url_for("main.index"))
