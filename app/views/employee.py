from flask import render_template, flash, redirect, url_for, Blueprint, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import and_
from app import db
from app.forms import DayOffRequestForm, WorkRequestForm, EmailEditForm, PasswordChangeForm
from app.models.user import get_selectable_shift_choices, EmploymentType
from app.models.day_off_request import DayOffRequest
from app.models.work_request import WorkRequest
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
    """希望休・希望勤務の申請と一覧表示、および最新シフトの表示"""
    day_off_form = DayOffRequestForm(prefix="day_off")
    work_request_form = WorkRequestForm(prefix="work_request")

    # 雇用形態に応じて希望勤務フォームを表示（全雇用形態で申請可能）
    # 選択肢は雇用形態に基づいてフィルタ
    employment_type = current_user.employment_type
    shift_choices = get_selectable_shift_choices(employment_type, exclude_kyu=True, coerce_int=True)
    work_request_form.shift_type_ids.choices = shift_choices

    if request.method == "POST":
        # どちらのフォームが送信されたかを判定
        if (
            "day_off-submit" in request.form
            and day_off_form.validate_on_submit()
        ):
            try:
                date_list_str = day_off_form.dates.data.split(', ')
                processed_dates = []
                for date_str in date_list_str:
                    if not date_str: continue
                    date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    req = DayOffRequest(
                        date=date, 
                        user_id=current_user.id,
                        request_type=day_off_form.request_type.data
                    )
                    db.session.add(req)
                    processed_dates.append(date_str)
                
                if processed_dates:
                    db.session.commit()
                    flash(
                        f'{", ".join(processed_dates)} の休み希望を申請しました。',
                        "success",
                    )
                else:
                    flash('日付が選択されていません。', 'warning')
                # 管理者へ通知メール
                # send_email(...)
            except Exception as e:
                db.session.rollback()
                flash(f"エラーが発生しました: {e}", "danger")
            return redirect(url_for("employee.dashboard"))

        elif (
            "work_request-submit" in request.form
            and work_request_form.validate_on_submit()
        ):
            try:
                date_obj = datetime.datetime.strptime(work_request_form.date.data, '%Y-%m-%d').date()
                req = WorkRequest(
                    date=date_obj,
                    user_id=current_user.id
                )
                # 選択されたShiftTypeオブジェクトを取得し、リレーションに追加
                shift_types = ShiftType.query.filter(
                    ShiftType.shift_type_id.in_(work_request_form.shift_type_ids.data)
                ).all()
                for st in shift_types:
                    req.shift_types.append(st)
                
                db.session.add(req)
                db.session.commit()
                flash(
                    f'{date_obj.strftime("%Y-%m-%d")} の希望勤務を申請しました。',
                    "success",
                )
                # 管理者へ通知メール
                # send_email(...)
            except Exception as e:
                db.session.rollback()
                flash(f"エラーが発生しました: {e}", "danger")
            return redirect(url_for("employee.dashboard"))

        # バリデーションエラーの表示
        if day_off_form.errors:
            for field, errors in day_off_form.errors.items():
                for error in errors:
                    flash(
                        f"{getattr(day_off_form, field).label.text}: {error}", "danger"
                    )
        if work_request_form.errors:
            for field, errors in work_request_form.errors.items():
                for error in errors:
                    flash(
                        f"{getattr(work_request_form, field).label.text}: {error}",
                        "danger",
                    )

    # 申請済みの一覧を取得
    day_off_requests = current_user.day_off_requests.order_by(
        DayOffRequest.date.desc()
    ).all()
    work_requests = current_user.work_requests.order_by(WorkRequest.date.desc()).all()

    # 最新の確定シフトを取得
    shifts = []
    shift_month_str = "未確定"
    latest_shift_record = (
        ShiftAssignment.query.filter(ShiftAssignment.user_id == current_user.id)
        .order_by(ShiftAssignment.date.desc())
        .first()
    )
    if latest_shift_record:
        target_year = latest_shift_record.date.year
        target_month = latest_shift_record.date.month
        shift_month_str = f"{target_year}年{target_month}月"
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
        day_off_form=day_off_form,
        work_request_form=work_request_form,
        employment_type=employment_type,
        day_off_requests=day_off_requests,
        work_requests=work_requests,
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

    # 'pending' 状態の申請のみ取り消し可能
    if req_to_delete.status != "pending":
        flash("承認済みまたは却下済みの申請は取り消せません。", "warning")
        return redirect(url_for("employee.dashboard"))

    try:
        db.session.delete(req_to_delete)
        db.session.commit()
        flash(f'{req_to_delete.date.strftime("%Y-%m-%d")} の申請を取り消しました。', "info")
    except Exception as e:
        db.session.rollback()
        flash(f"エラーが発生しました: {e}", "danger")
    return redirect(url_for("employee.dashboard"))


@employee_bp.route("/work_request/delete/<int:request_id>", methods=["POST"])
@login_required
def delete_work_request(request_id):
    """希望勤務申請を取り消す"""
    req_to_delete = db.get_or_404(WorkRequest, request_id)

    if req_to_delete.user_id != current_user.id:
        flash("権限がありません。", "danger")
        return redirect(url_for("employee.dashboard"))

    if req_to_delete.status != "pending":
        flash("承認済みまたは却下済みの申請は取り消せません。", "warning")
        return redirect(url_for("employee.dashboard"))

    try:
        db.session.delete(req_to_delete)
        db.session.commit()
        flash(f'{req_to_delete.date.strftime("%Y-%m-%d")} の希望勤務申請を取り消しました。', "info")
    except Exception as e:
        db.session.rollback()
        flash(f"エラーが発生しました: {e}", "danger")

    return redirect(url_for("employee.dashboard"))


@employee_bp.route("/edit_email", methods=["GET", "POST"])
@login_required
def edit_email():
    """従業員が自身のメールアドレスを編集する"""
    form = EmailEditForm(original_email=current_user.email)
    if form.validate_on_submit():
        if not current_user.check_password(form.password.data):
            flash("パスワードが正しくありません。", "danger")
            return redirect(url_for("employee.edit_email"))
        try:
            current_user.email = form.email.data
            db.session.commit()
            flash("メールアドレスを更新しました。", "success")
            return redirect(url_for("employee.dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")
    
    elif request.method == "GET":
        form.email.data = current_user.email

    # バリデーション失敗時のエラー表示
    if request.method == "POST":
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")

    return render_template("employee/edit_email.html", title="メールアドレス変更", form=form)


@employee_bp.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """従業員が自身のパスワードを変更する"""
    form = PasswordChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("現在のパスワードが正しくありません。", "danger")
            return redirect(url_for("employee.change_password"))
        
        # 新しいパスワードが現在のパスワードと同じでないことを確認
        if current_user.check_password(form.new_password.data):
            flash("新しいパスワードが現在のパスワードと同じです。別のパスワードを設定してください。", "danger")
            return redirect(url_for("employee.change_password"))

        try:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("パスワードを更新しました。", "success")
            return redirect(url_for("employee.dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")

    # バリデーション失敗時のエラー表示
    if request.method == "POST":
        for field, errors in form.errors.items():
            for error in errors:
                 flash(f"{getattr(form, field).label.text}: {error}", "danger")
    
    return render_template("employee/change_password.html", title="パスワード変更", form=form)


