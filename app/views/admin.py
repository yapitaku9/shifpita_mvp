from flask import render_template, flash, redirect, url_for, Blueprint, request, current_app, send_from_directory
from flask_login import login_required, current_user
from app import db
from app.forms import EmployeeForm, ShiftGenerationForm, create_shift_constraint_form, SpecialDayForm, EmailEditForm, PasswordChangeForm, UsernameChangeForm
from app.models.user import User
from app.models.master import ShiftConstraint
from app.models.history import ShiftGenerationHistory
from app.models.special_day import SpecialDay
from app.models.day_off_request import DayOffRequest
from app.models.work_request import WorkRequest
from app.services.generator import ShiftGenerator
from app.services.pdf_exporter import PDFExporter
from app.email import send_email
import datetime
import os

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


@admin_bp.route("/", methods=["GET", "POST"])
def dashboard():
    """従業員の一覧表示と追加処理 (管理者ダッシュボード)"""
    form = EmployeeForm()
    gen_form = ShiftGenerationForm()  # シフト生成フォーム

    # 従業員追加フォームのPOSTリクエストを処理
    # テンプレート側で form.submit の name 属性を 'submit_employee' などに設定して区別する想定
    if form.validate_on_submit() and request.form.get("form_name") == "employee_form":
        try:
            user = User(username=form.username.data, email=form.email.data or None, role_id=form.role.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f"従業員「{user.username}」を追加しました。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")
        return redirect(url_for("admin.dashboard"))

    # EmployeeFormのバリデーションが失敗した場合のエラー表示
    if request.method == "POST" and request.form.get("form_name") == "employee_form":
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")

    user_list = User.query.filter_by(is_admin=False).order_by(User.username).all()
    
    # シフト生成履歴を取得 (最新5件)
    history_list = ShiftGenerationHistory.query.order_by(ShiftGenerationHistory.generation_timestamp.desc()).limit(5).all()
    
    return render_template(
        "admin/dashboard.html",
        title="管理者ダッシュボード",
        form=form,
        gen_form=gen_form,
        users=user_list,
        history_list=history_list
    )


@admin_bp.route("/download_pdf/<int:history_id>")
def download_pdf(history_id):
    """生成されたシフトPDFをダウンロードする"""
    history = db.get_or_404(ShiftGenerationHistory, history_id)
    if history.pdf_file_path and history.status == 'Success':
        pdf_dir = os.path.join(current_app.instance_path, 'pdfs')
        return send_from_directory(pdf_dir, history.pdf_file_path, as_attachment=True)
    else:
        flash("PDFファイルが見つからないか、生成に失敗しています。", "danger")
        return redirect(url_for('admin.dashboard'))




@admin_bp.route("/generate", methods=["POST"])
def generate_shifts():
    """シフト生成を実行し、履歴とPDFを保存する"""
    form = ShiftGenerationForm()
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")
        return redirect(url_for("admin.dashboard"))

    year = form.year.data
    month = form.month.data
    flash(f"{year}年{month}月のシフト生成を開始します...", "info")

    history = ShiftGenerationHistory(
        target_year=year,
        target_month=month,
        status="In Progress"
    )
    db.session.add(history)
    db.session.commit()

    try:
        generator = ShiftGenerator()
        # 戻り値を success と result (成功時はデータ、失敗時はエラーメッセージ) で受け取る
        success, result = generator.run(year, month)

        if success:
            assignments_for_pdf = result # 成功時はPDF用データ
            
            # PDF生成
            all_users = User.query.filter_by(is_admin=False).all()
            employees_for_pdf = [{"id": u.id, "name": u.username} for u in all_users]
            
            pdf_exporter = PDFExporter()
            pdf_data = pdf_exporter.generate(year, month, employees_for_pdf, assignments_for_pdf)
            
            # PDF保存
            pdf_dir = os.path.join(current_app.instance_path, 'pdfs')
            os.makedirs(pdf_dir, exist_ok=True)
            timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            pdf_filename = f"shift_{year}_{month:02d}_{timestamp}.pdf"
            pdf_path = os.path.join(pdf_dir, pdf_filename)
            
            with open(pdf_path, 'wb') as f:
                f.write(pdf_data)

            # 履歴を更新
            history.status = "Success"
            history.pdf_file_path = pdf_filename # Store relative path from pdf_dir
            flash(f"{year}年{month}月のシフトが正常に作成・保存されました。", "success")
        else:
            # 失敗時は result がエラーメッセージ
            error_message = result
            history.status = "Failed"
            flash(error_message, "danger")

    except Exception as e:
        history.status = "Failed"
        flash(f"シフト生成中に予期せぬエラーが発生しました: {e}", "danger")
        # Log the full error for debugging
        current_app.logger.error(f"Shift generation failed: {e}", exc_info=True)
    finally:
        db.session.commit()

    return redirect(url_for("admin.dashboard"))



@admin_bp.route("/constraints", methods=["GET", "POST"])
def manage_constraints():
    """シフト作成の制約条件と特別日を編集する"""
    ShiftConstraintForm = create_shift_constraint_form()
    form = ShiftConstraintForm()
    special_day_form = SpecialDayForm()

    # POSTリクエストの判別
    if request.method == 'POST':
        # name属性でどちらのフォームが送信されたかを判断
        if 'submit_constraints' in request.form and form.validate_on_submit():
            try:
                for field_name, field_value in form.data.items():
                    if field_name not in ['csrf_token', 'submit', 'submit_constraints']:
                        constraint = ShiftConstraint.query.filter_by(name=field_name).first()
                        if constraint and constraint.value != field_value:
                            constraint.value = field_value
                db.session.commit()
                flash("制約条件を更新しました。", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"制約条件の更新中にエラーが発生しました: {e}", "danger")
            return redirect(url_for("admin.manage_constraints"))

        elif 'submit_special_day' in request.form and special_day_form.validate_on_submit():
            try:
                special_day = SpecialDay(
                    date=special_day_form.date.data,
                    staff_increase=special_day_form.staff_increase.data,
                    description=special_day_form.description.data
                )
                db.session.add(special_day)
                db.session.commit()
                flash(f"{special_day.date.strftime('%Y-%m-%d')}を特別日として設定しました。", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"特別日の設定中にエラーが発生しました: {e}", "danger")
            return redirect(url_for("admin.manage_constraints"))

    # GETリクエストの場合、またはフォームバリデーションが失敗した場合の処理
    # --- 制約条件の処理 ---
    if request.method == "GET":
        default_constraints = {
            "max_part3_late_shifts": {"description": "【パート】パート3 月間遅番上限", "value": 6},
        }
        try:
            with db.session.begin_nested():
                for name, data in default_constraints.items():
                    if not db.session.query(ShiftConstraint).filter_by(name=name).first():
                        db.session.add(ShiftConstraint(name=name, description=data["description"], value=data["value"]))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error setting default constraints: {e}")

        # フォームを再生成してDBの値を反映
        ShiftConstraintForm = create_shift_constraint_form()
        form = ShiftConstraintForm()
        for constraint in ShiftConstraint.query.all():
            if hasattr(form, constraint.name):
                getattr(form, constraint.name).data = constraint.value
    
    # --- ラベルとグループの整形 ---
    label_overrides = {
        "max_part3_late_shifts": "【勤務回数】パート3の月間遅番回数",
        "monthly_work_days_kaigo": "【勤務回数】「正規雇用労働者」の月間勤務日数"
    }
    unification_group_name = "【勤務回数】"
    target_groups = ["【パート】", "【回数上限】", "【夜勤】", "【月間勤務】"]

    for field in form:
        if field.type not in ['CSRFTokenField', 'SubmitField']:
            if field.name in label_overrides:
                field.label.text = label_overrides[field.name]

            label_text = field.label.text
            original_group = ""
            if '】' in label_text:
                original_group = label_text.split('】')[0] + '】'
            
            if original_group in target_groups:
                field.group = unification_group_name
            elif original_group:
                field.group = original_group
            else:
                field.group = 'その他'

    # --- 特別日のリストを取得 ---
    special_days = SpecialDay.query.order_by(SpecialDay.date.asc()).all()

    return render_template(
        "admin/constraints.html",
        title="制約条件・特別日の編集",
        form=form,
        special_day_form=special_day_form,
        special_days=special_days
    )


@admin_bp.route("/delete_special_day/<int:day_id>", methods=['POST'])
@login_required
def delete_special_day(day_id):
    """特別日を削除する"""
    if not current_user.is_admin:
        flash("この操作には管理者権限が必要です。")
        return redirect(url_for("main.index"))
    
    day_to_delete = db.get_or_404(SpecialDay, day_id)
    try:
        db.session.delete(day_to_delete)
        db.session.commit()
        flash(f"{day_to_delete.date.strftime('%Y-%m-%d')}の特別日設定を削除しました。", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"削除中にエラーが発生しました: {e}", "danger")
    return redirect(url_for('admin.manage_constraints'))


@admin_bp.route("/edit_employee/<int:user_id>", methods=['GET', 'POST'])
def edit_employee(user_id):
    """従業員情報を編集する"""
    user = db.get_or_404(User, user_id)
    # EmployeeFormのコンストラクタで 'Role' をクエリするため、appコンテキストが必要
    from app.models.master import Role, ShiftType

    form = EmployeeForm(original_username=user.username, original_email=user.email)

    # パート4用のシフト選択肢をフォームに設定
    part4_shifts = ShiftType.query.filter(ShiftType.name.in_(["1", "2", "3", "4", "5", "6", "7", "8"])).order_by(ShiftType.name).all()
    form.workable_shifts.choices = [(s.shift_type_id, s.name) for s in part4_shifts]

    if form.validate_on_submit():
        try:
            user.username = form.username.data
            user.email = form.email.data or None
            user.role_id = form.role.data
            
            new_role = db.session.get(Role, form.role.data)
            if new_role and new_role.name.startswith("パート"):
                user.desired_work_days = form.desired_work_days.data
            else:
                user.desired_work_days = None

            if new_role and new_role.name == "パート4":
                user.workable_shifts.clear()
                selected_shift_ids = form.workable_shifts.data
                selected_shifts = ShiftType.query.filter(ShiftType.shift_type_id.in_(selected_shift_ids)).all()
                for shift in selected_shifts:
                    user.workable_shifts.append(shift)
            else:
                user.workable_shifts.clear()
            
            if form.password.data:
                user.set_password(form.password.data)
            db.session.commit()
            flash(f"従業員「{user.username}」の情報を更新しました。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")
        return redirect(url_for('admin.dashboard'))

    elif request.method == 'GET':
        form.username.data = user.username
        form.email.data = user.email
        form.role.data = user.role_id
        if user.role:
            if user.role.name.startswith("パート"):
                form.desired_work_days.data = user.desired_work_days
            if user.role.name == "パート4":
                form.workable_shifts.data = [s.shift_type_id for s in user.workable_shifts]

    return render_template('admin/edit_employee.html', title='従業員の編集', form=form, user=user)


@admin_bp.route("/delete_employee/<int:user_id>", methods=['POST'])
def delete_employee(user_id):
    """従業員を削除する"""
    user = db.get_or_404(User, user_id)
    try:
        # TODO: 関連するシフトデータなども削除、あるいは無効化する処理が必要か検討
        db.session.delete(user)
        db.session.commit()
        flash(f"従業員「{user.username}」を削除しました。", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"エラーが発生しました: {e}", "danger")
    return redirect(url_for('admin.dashboard'))


@admin_bp.route("/day_off_requests")
def manage_day_off_requests():
    """希望休の申請を一覧表示し、管理する"""
    status_filter = request.args.get('status', 'pending')  # デフォルトは 'pending'

    query = DayOffRequest.query.join(User).order_by(DayOffRequest.date.asc())

    if status_filter and status_filter != 'all':
        query = query.filter(DayOffRequest.status == status_filter)

    requests = query.all()

    # タブの各件数を計算
    count_all = DayOffRequest.query.count()
    count_pending = DayOffRequest.query.filter_by(status='pending').count()
    count_approved = DayOffRequest.query.filter_by(status='approved').count()
    count_rejected = DayOffRequest.query.filter_by(status='rejected').count()

    return render_template(
        "admin/day_off_requests.html",
        title="希望休申請の管理",
        requests=requests,
        current_status=status_filter,
        counts={
            'all': count_all,
            'pending': count_pending,
            'approved': count_approved,
            'rejected': count_rejected
        }
    )


@admin_bp.route("/day_off_requests/<int:request_id>/<string:action>", methods=['POST'])
def action_day_off_request(request_id, action):
    """希望休申請を承認または却下する"""
    req = db.get_or_404(DayOffRequest, request_id)
    
    if action == 'approve':
        req.status = 'approved'
        flash(f'{req.user.username}さんの {req.date.strftime("%Y-%m-%d")} の希望休を承認しました。', 'success')
    elif action == 'reject':
        req.status = 'rejected'
        flash(f'{req.user.username}さんの {req.date.strftime("%Y-%m-%d")} の希望休を却下しました。', 'warning')
    else:
        flash('無効な操作です。', 'danger')
        return redirect(url_for('admin.manage_day_off_requests'))

    try:
        db.session.commit()
        # TODO: 従業員への通知メールを送信する
        # send_email(...)
    except Exception as e:
        db.session.rollback()
        flash(f"処理中にエラーが発生しました: {e}", "danger")

    # 元のフィルタ状態を維持してリダイレクト
    status_filter = request.args.get('status', 'pending')
    return redirect(url_for('admin.manage_day_off_requests', status=status_filter))


@admin_bp.route("/work_requests")
def manage_work_requests():
    """希望勤務の申請を一覧表示し、管理する"""
    status_filter = request.args.get('status', 'pending')

    query = WorkRequest.query.join(User).order_by(WorkRequest.date.asc())

    if status_filter and status_filter != 'all':
        query = query.filter(WorkRequest.status == status_filter)

    requests = query.all()

    # タブの各件数を計算
    count_all = WorkRequest.query.count()
    count_pending = WorkRequest.query.filter_by(status='pending').count()
    count_approved = WorkRequest.query.filter_by(status='approved').count()
    count_rejected = WorkRequest.query.filter_by(status='rejected').count()

    return render_template(
        "admin/work_requests.html",
        title="希望勤務申請の管理",
        requests=requests,
        current_status=status_filter,
        counts={
            'all': count_all,
            'pending': count_pending,
            'approved': count_approved,
            'rejected': count_rejected
        }
    )


@admin_bp.route("/work_requests/<int:request_id>/<string:action>", methods=['POST'])
def action_work_request(request_id, action):
    """希望勤務申請を承認または却下する"""
    req = db.get_or_404(WorkRequest, request_id)
    
    if action == 'approve':
        req.status = 'approved'
        flash(f'{req.user.username}さんの {req.date.strftime("%Y-%m-%d")} の希望勤務 ({req.shift_type.name}) を承認しました。', 'success')
    elif action == 'reject':
        req.status = 'rejected'
        flash(f'{req.user.username}さんの {req.date.strftime("%Y-%m-%d")} の希望勤務 ({req.shift_type.name}) を却下しました。', 'warning')
    else:
        flash('無効な操作です。', 'danger')
        return redirect(url_for('admin.manage_work_requests'))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"処理中にエラーが発生しました: {e}", "danger")

    status_filter = request.args.get('status', 'pending')
    return redirect(url_for('admin.manage_work_requests', status=status_filter))


@admin_bp.route("/edit_username", methods=["GET", "POST"])
@login_required
def edit_username():
    """管理者が自身のユーザー名を変更する"""
    form = UsernameChangeForm(original_username=current_user.username)
    if form.validate_on_submit():
        if not current_user.check_password(form.password.data):
            flash("パスワードが正しくありません。", "danger")
            return redirect(url_for("admin.edit_username"))
        try:
            current_user.username = form.username.data
            db.session.commit()
            flash("ユーザーIDを更新しました。", "success")
            return redirect(url_for("admin.dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")

    elif request.method == "GET":
        form.username.data = current_user.username
    
    # バリデーション失敗時のエラー表示
    if request.method == "POST":
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")

    return render_template("admin/edit_username.html", title="ユーザーID変更", form=form)


@admin_bp.route("/edit_email", methods=["GET", "POST"])
@login_required
def edit_email():
    """管理者が自身のメールアドレスを編集する"""
    form = EmailEditForm(original_email=current_user.email)
    if form.validate_on_submit():
        if not current_user.check_password(form.password.data):
            flash("パスワードが正しくありません。", "danger")
            return redirect(url_for("admin.edit_email"))
        try:
            current_user.email = form.email.data
            db.session.commit()
            flash("メールアドレスを更新しました。", "success")
            return redirect(url_for("admin.dashboard"))
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

    return render_template("admin/edit_email.html", title="メールアドレス変更", form=form)


@admin_bp.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """管理者が自身のパスワードを変更する"""
    form = PasswordChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("現在のパスワードが正しくありません。", "danger")
            return redirect(url_for("admin.change_password"))
        
        # 新しいパスワードが現在のパスワードと同じでないことを確認
        if current_user.check_password(form.new_password.data):
            flash("新しいパスワードが現在のパスワードと同じです。別のパスワードを設定してください。", "danger")
            return redirect(url_for("admin.change_password"))

        try:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("パスワードを更新しました。", "success")
            return redirect(url_for("admin.dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")

    # バリデーション失敗時のエラー表示
    if request.method == "POST":
        for field, errors in form.errors.items():
            for error in errors:
                 flash(f"{getattr(form, field).label.text}: {error}", "danger")
    
    return render_template("admin/change_password.html", title="パスワード変更", form=form)
