from flask import render_template, flash, redirect, url_for, Blueprint, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import and_
from app import db
from app.forms import DayOffRequestForm
from app.models.day_off_request import DayOffRequest
from app.models.shift import ShiftAssignment
from app.models.master import ShiftType
from app.email import send_email
import datetime

employee_bp = Blueprint("employee", __name__, url_prefix="/employee")


@employee_bp.before_request
@login_required
def before_request():
    """
    ブループリント内の全ルートで実行される共通処理。
    管理者ユーザーであれば管理者ダッシュボードへリダイレクトする。
    """
    if current_user.is_admin:
        flash("このページは従業員専用です。管理者ダッシュボードに移動しました。")
        return redirect(url_for("main.index"))


@employee_bp.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    """希望休の申請と一覧表示、および最新シフトの表示"""
    form = DayOffRequestForm()
    if form.validate_on_submit():
        try:
            req = DayOffRequest(date=form.date.data, user_id=current_user.id)
            db.session.add(req)
            db.session.commit()
            flash(f'{form.date.data.strftime("%Y-%m-%d")} の希望休を申請しました。', "success")

            # 管理者へ通知メールを送信
            send_email(
                subject="[シフぴた] 希望休の申請通知",
                recipients=current_app.config["ADMINS"],
                template="day_off_notification",
                user=current_user,
                request=req,
            )
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")
        return redirect(url_for("employee.dashboard"))

    if request.method == "POST":  # validate_on_submitがFalseだった場合
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")

    # 未来の申請のみ表示
    requests = (
        DayOffRequest.query.filter(
            DayOffRequest.user_id == current_user.id, DayOffRequest.date >= datetime.date.today()
        )
        .order_by(DayOffRequest.date.asc())
        .all()
    )

    # 最新の確定シフトを取得
    shifts = []
    shift_month_str = "未確定"

    # ユーザーに紐づく最新のシフト日を取得
    latest_shift_record = ShiftAssignment.query.filter(
        ShiftAssignment.user_id == current_user.id
    ).order_by(ShiftAssignment.date.desc()).first()

    if latest_shift_record:
        target_year = latest_shift_record.date.year
        target_month = latest_shift_record.date.month
        shift_month_str = f"{target_year}年{target_month}月"

        # 最新年月のシフトを全て取得
        shifts = (
            ShiftAssignment.query.join(ShiftType)
            .filter(
                and_(
                    ShiftAssignment.user_id == current_user.id,
                    db.extract("year", ShiftAssignment.date) == target_year,
                    db.extract("month", ShiftAssignment.date) == target_month,
                )
            )
            .order_by(ShiftAssignment.date.asc())
            .all()
        )

    return render_template(
        "employee/dashboard.html",
        title="従業員ダッシュボード",
        form=form,
        requests=requests,
        shifts=shifts,
        shift_month_str=shift_month_str,
    )


@employee_bp.route("/day_off/delete/<int:request_id>", methods=["POST"])
def delete_day_off(request_id):
    """希望休申請を取り消す"""
    req_to_delete = db.get_or_404(DayOffRequest, request_id)

    # 自分の申請以外は削除できないようにする
    if req_to_delete.user_id != current_user.id:
        flash("権限がありません。", "danger")
        return redirect(url_for("employee.dashboard"))

    try:
        db.session.delete(req_to_delete)
        db.session.commit()
        flash(f'{req_to_delete.date.strftime("%Y-%m-%d")} の申請を取り消しました。', "info")
    except Exception as e:
        db.session.rollback()
        flash(f"エラーが発生しました: {e}", "danger")

    return redirect(url_for("employee.dashboard"))
