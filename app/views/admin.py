from flask import render_template, flash, redirect, url_for, Blueprint, request, current_app, send_from_directory
from flask_login import login_required, current_user
from app import db
from app.forms import EmployeeForm, ShiftGenerationForm, create_shift_constraint_form
from app.models.user import User
from app.models.master import ShiftConstraint
from app.models.history import ShiftGenerationHistory
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
        success, assignments_for_pdf = generator.run(year, month)

        if success:
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
            history.status = "Failed"
            flash("シフトの作成に失敗しました。制約条件を見直してください。", "danger")

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
    """シフト作成の制約条件を編集する"""
    ShiftConstraintForm = create_shift_constraint_form()
    form = ShiftConstraintForm()

    if form.validate_on_submit():
        try:
            for field_name, field_value in form.data.items():
                if field_name not in ['csrf_token', 'submit']:
                    constraint = ShiftConstraint.query.filter_by(name=field_name).first()
                    if constraint and constraint.value != field_value:
                        constraint.value = field_value
            db.session.commit()
            flash("制約条件を更新しました。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")
        return redirect(url_for("admin.manage_constraints"))

    # GETリクエストの場合、DBから現在の値を読み込んでフォームに設定
    if request.method == 'GET':
        constraints = ShiftConstraint.query.all()
        for constraint in constraints:
            if hasattr(form, constraint.name):
                field = getattr(form, constraint.name)
                field.data = constraint.value
    
    # Add a 'group' attribute to each field for template-side grouping
    for field in form:
        if field.type not in ['CSRFTokenField', 'SubmitField']:
            label_text = field.label.text
            if '】' in label_text:
                field.group = label_text.split('】')[0] + '】'
            else:
                field.group = 'その他'


    return render_template(
        "admin/constraints.html",
        title="制約条件の編集",
        form=form
    )


@admin_bp.route("/edit_employee/<int:user_id>", methods=['GET', 'POST'])
def edit_employee(user_id):
    """従業員情報を編集する"""
    user = db.get_or_404(User, user_id)
    form = EmployeeForm(original_username=user.username, original_email=user.email)

    if form.validate_on_submit():
        try:
            user.username = form.username.data
            user.email = form.email.data or None
            user.role_id = form.role.data
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
