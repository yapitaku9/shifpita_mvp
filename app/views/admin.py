from flask import render_template, flash, redirect, url_for, Blueprint, request, current_app, send_from_directory, jsonify, send_file
from flask_login import login_required, current_user
from sqlalchemy import func, case
from wtforms import BooleanField
from app import db
from app.forms import EmployeeForm, ShiftGenerationForm, ShiftConfirmationForm, ShiftConstraintForm, SpecialDayForm, EmailEditForm, PasswordChangeForm, UsernameChangeForm
from app.models.user import User, EmploymentType, get_selectable_shift_choices
from app.models.master import ShiftConstraint, ShiftType
from app.models.history import ShiftGenerationHistory
from app.models.shift import ShiftAssignment
from app.models.shift_history import ShiftHistory
from app.models.special_day import SpecialDay
from app.models.day_off_request import DayOffRequest
from app.models.work_request import WorkRequest
from app.services.generator import ShiftGenerator
from app.services.pdf_exporter import PDFExporter
from app.services.excel_exporter import ExcelExporter
from app.email import send_email
import datetime
import os
import io
import calendar
from collections import defaultdict

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
    # 追加フォーム: 雇用形態の初期値でシフト選択肢を設定
    form = EmployeeForm(employment_type=EmploymentType.FULL_TIME)
    gen_form = ShiftGenerationForm()  # シフト生成フォーム
    confirm_form = ShiftConfirmationForm() # シフト確定フォーム

    # 従業員追加フォームのPOSTリクエストを処理
    # テンプレート側で form.submit の name 属性を 'submit_employee' などに設定して区別する想定
    if form.validate_on_submit() and request.form.get("form_name") == "employee_form":
        try:
            employment_type_enum = EmploymentType[form.employment_type.data]
            ng_shifts_str = ",".join(map(str, form.ng_shifts.data))

            user = User(
                username=form.username.data,
                full_name=form.full_name.data,
                employee_number=form.employee_number.data,
                email=form.email.data or None,
                employment_type=employment_type_enum,
                max_consecutive_work_days=form.max_consecutive_work_days.data,
                min_work_days=form.min_work_days.data,
                max_work_days=form.max_work_days.data,
                min_night_shifts=form.min_night_shifts.data,
                max_night_shifts=form.max_night_shifts.data,
                preferred_shift_1_id=form.preferred_shift_1.data,
                preferred_shift_2_id=form.preferred_shift_2.data,
                ng_shifts=ng_shifts_str
            )
            if form.password.data:
                user.set_password(form.password.data)
            else:
                # 新規作成時はパスワードが必須
                flash("新規従業員登録にはパスワードが必要です。", "danger")
                # redirectする前にフォームエラーを再表示させるため、ここでrenderする
                user_list = User.query.filter_by(is_admin=False).order_by(User.username).all()
                history_list = ShiftGenerationHistory.query.order_by(ShiftGenerationHistory.generation_timestamp.desc()).limit(5).all()
                return render_template(
                    "admin/dashboard.html",
                    title="管理者ダッシュボード",
                    form=form,
                    gen_form=gen_form,
                    confirm_form=confirm_form,
                    users=user_list,
                    history_list=history_list
                )

            db.session.add(user)
            db.session.commit()
            flash(f"従業員「{user.full_name}」を追加しました。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")
        return redirect(url_for("admin.dashboard"))

    # EmployeeFormのバリデーションが失敗した場合のエラー表示と選択肢の再設定
    if request.method == "POST" and request.form.get("form_name") == "employee_form":
        emp_type_str = request.form.get("employment_type")
        if emp_type_str:
            try:
                form.set_shift_choices_by_employment(EmploymentType[emp_type_str])
            except (KeyError, TypeError):
                pass
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")

    sort_order_employment = case(
        (User.employment_type == EmploymentType.MANAGER, 1),
        (User.employment_type == EmploymentType.SUPPORT, 2),
        (User.employment_type == EmploymentType.FULL_TIME, 3),
        (User.employment_type == EmploymentType.PART_TIME_8H, 4),
        (User.employment_type == EmploymentType.PART_TIME_SHORT, 5),
        else_=6
    )
    user_list = User.query.filter_by(is_admin=False).order_by(
        User.employee_number.asc().nulls_last(),
        sort_order_employment,
        User.full_name
    ).all()
    
    # シフト生成履歴を取得 (最新5件)
    history_list = ShiftGenerationHistory.query.order_by(ShiftGenerationHistory.generation_timestamp.desc()).limit(5).all()
    
    # 各種申請の未処理件数を取得
    pending_day_off_count = DayOffRequest.query.filter_by(status='pending').count()
    pending_work_request_count = WorkRequest.query.filter_by(status='pending').count()

    return render_template(
        "admin/dashboard.html",
        title="管理者ダッシュボード",
        form=form,
        gen_form=gen_form,
        confirm_form=confirm_form,
        users=user_list,
        history_list=history_list,
        pending_day_off_count=pending_day_off_count,
        pending_work_request_count=pending_work_request_count,
    )


@admin_bp.route("/shift_choices/<employment_type>")
def get_shift_choices(employment_type):
    """雇用形態に応じたシフト選択肢をJSONで返す（フォームの動的更新用）"""
    try:
        et = EmploymentType[employment_type]
    except (KeyError, TypeError):
        return jsonify({"error": "Invalid employment type"}), 400
    ng_choices = get_selectable_shift_choices(et, exclude_kyu=True, coerce_int=True)
    pref_choices = get_selectable_shift_choices(et, include_blank=True, coerce_int=True)
    return jsonify({
        "ng_shifts": [{"id": tid, "name": name} for tid, name in ng_choices],
        "preferred_shifts": [{"id": tid if tid is not None else "", "name": name} for tid, name in pref_choices]
    })





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
        success, result = generator.run(year, month)

        if success:
            assignments_for_pdf = result
            
            # --- 前月5日間のデータを取得 ---
            prev_month_date = datetime.date(year, month, 1) - datetime.timedelta(days=1)
            prev_month_start_date = prev_month_date.replace(day=1)
            # For headcount calculation, we need at least the last day of the previous month.
            # For display, we need the last 5 days. Get 5 days for both.
            pm_first_day_to_get = prev_month_date - datetime.timedelta(days=4)
            
            prev_month_shifts_raw = ShiftHistory.query.filter(
                ShiftHistory.date.between(pm_first_day_to_get, prev_month_date)
            ).all()

            prev_month_assignments = [
                {"date": s.date.isoformat(), "employee_id": s.user_id, "shift_type": s.shift_type.name}
                for s in prev_month_shifts_raw
            ]
            
            # 結合
            full_assignments = prev_month_assignments + assignments_for_pdf

            history.status = "Success"
            # history.pdf_file_path = pdf_filename
            flash(f"{year}年{month}月のシフトが正常に作成されました。", "success")
        else:
            error_message = result
            history.status = "Failed"
            flash(error_message, "danger")

    except Exception as e:
        history.status = "Failed"
        flash(f"シフト生成中に予期せぬエラーが発生しました: {e}", "danger")
        current_app.logger.error(f"Shift generation failed: {e}", exc_info=True)
    finally:
        db.session.commit()

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/confirm_overwrite/<int:year>/<int:month>", methods=['GET'])
@login_required
def confirm_overwrite(year, month):
    """Render the overwrite confirmation page."""
    form = ShiftConfirmationForm(year=year, month=month)
    return render_template("admin/confirm_overwrite.html", form=form, year=year, month=month, title="上書き確認")


@admin_bp.route("/confirm", methods=["POST"])
def confirm_shifts():
    """生成されたシフトを履歴に保存して確定する"""
    form = ShiftConfirmationForm()
    overwrite = request.form.get('overwrite') == 'true'
    
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")
        return redirect(url_for("admin.dashboard"))

    year = form.year.data
    month = form.month.data
    
    start_date = datetime.date(year, month, 1)
    end_date = datetime.date(year, month, calendar.monthrange(year, month)[1])

    if not overwrite:
        existing_history = ShiftHistory.query.filter(
            ShiftHistory.date >= start_date,
            ShiftHistory.date <= end_date
        ).first()
        if existing_history:
            return redirect(url_for('admin.confirm_overwrite', year=year, month=month))

    try:
        # この月の既存の履歴を削除
        ShiftHistory.query.filter(
            ShiftHistory.date >= start_date,
            ShiftHistory.date <= end_date
        ).delete(synchronize_session=False)

        # 現在の割り当てを取得
        assignments_to_confirm = ShiftAssignment.query.filter(
            ShiftAssignment.date >= start_date,
            ShiftAssignment.date <= end_date
        ).all()

        if not assignments_to_confirm:
            flash(f"{year}年{month}月には確定できるシフトがありません。", "warning")
            return redirect(url_for("admin.dashboard"))

        # 履歴にコピー
        history_entries = []
        for assign in assignments_to_confirm:
            history_entries.append(
                ShiftHistory(
                    date=assign.date,
                    user_id=assign.user_id,
                    shift_type_id=assign.shift_type_id,
                )
            )
        
        db.session.bulk_save_objects(history_entries)
        db.session.commit()
        
        if overwrite:
            flash(f"{year}年{month}月のシフトを上書きしました。", "success")
        else:
            flash(f"{year}年{month}月のシフトを確定しました。", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"シフトの確定中にエラーが発生しました: {e}", "danger")
        current_app.logger.error(f"Shift confirmation failed: {e}", exc_info=True)

    return redirect(url_for("admin.dashboard"))



from app.models.master import ShiftConstraint, ShiftType, ConstraintType
@admin_bp.route("/constraints", methods=["GET", "POST"])
def manage_constraints():
    """シフト作成の制約条件と特別日を編集する"""
    if not current_user.is_admin:
        flash('管理者権限が必要です。')
        return redirect(url_for('main.index'))

    # マスター制約リスト (ユーザー指定のものに限定)
    master_constraints = [
        # 希望休・勤務
        {'name': 'respect_day_off_requests', 'category': '希望休・勤務', 'description_jp': '希望休の厳守'},
        {'name': 'respect_work_requests', 'category': '希望休・勤務', 'description_jp': '希望勤務の厳守'},
        {'name': 'respect_ng_shifts', 'category': '希望休・勤務', 'description_jp': 'NG勤務の厳守'},
        {'name': 'prefer_paid_leave_as_holiday', 'category': '希望休・勤務', 'description_jp': '希望有給休暇に”休”を優先'},
        {'name': 'penalty_for_not_assigning_preferred_shift', 'category': '希望休・勤務', 'description_jp': '優先シフト非採用'},
        
        # 連勤・連続シフト
        {'name': 'max_consecutive_work', 'category': '連勤・連続シフト', 'description_jp': '最大連勤日数'},
        {'name': 'max_consecutive_night_shifts', 'category': '連勤・連続シフト', 'description_jp': '夜勤の最大連勤日数'},
        {'name': 'max_consecutive_late_shifts', 'category': '連勤・連続シフト', 'description_jp': '遅番の最大連続日数'},
        {'name': 'max_consecutive_late_night_shifts', 'category': '連勤・連続シフト', 'description_jp': '遅番・夜勤の最大連勤日数'},
        {'name': 'avoid_5_consecutive_work_days', 'category': '連勤・連続シフト', 'description_jp': '5連続勤務の回避'},
        {'name': 'avoid_4_consecutive_night_shifts', 'category': '連勤・連続シフト', 'description_jp': '4連続夜勤の回避'},
        {'name': 'avoid_4_consecutive_late_shifts', 'category': '連勤・連続シフト', 'description_jp': '4連続遅番の回避'},
        {'name': 'holiday_after_ake', 'category': '連勤・連続シフト', 'description_jp': '明けの翌日は休み'},

        # シフト間のルール
        {'name': 'forbidden_shift_after_night_shift', 'category': 'シフト間のルール', 'description_jp': '夜勤翌日の禁止シフト(遅日早)'},
        {'name': 'forbidden_shift_after_late_shift', 'category': 'シフト間のルール', 'description_jp': '遅番翌日の禁止シフト(日早)'},
        {'name': 'forbidden_shift_after_day_shift', 'category': 'シフト間のルール', 'description_jp': '日勤翌日の禁止シフト(早)'},
        {'name': 'no_consecutive_same_category_shifts', 'category': 'シフト間のルール', 'description_jp': '早番や日勤などの同シフトにおける２から１の移行禁止'},

        # 公平性
        {'name': 'penalty_for_work_day_violation', 'category': '公平性', 'description_jp': '勤務日数の不足・超過'},
        {'name': 'penalty_for_night_shift_violation', 'category': '公平性', 'description_jp': '夜勤日数の不足・超過'},

        # 人員の過不足
        {'name': 'no_staff_variance_07_20', 'category': '人員の過不足', 'description_jp': '過不足を完全に禁止 (07:00-20:00)'},
        {'name': 'penalty_shortage_07_20', 'category': '人員の過不足', 'description_jp': '人員不足ペナルティ (07:00-20:00)'},
        {'name': 'penalty_surplus_1_07_20', 'category': '人員の過不足', 'description_jp': '1人超過ペナルティ (07:00-20:00)'},
        {'name': 'penalty_surplus_2_07_20', 'category': '人員の過不足', 'description_jp': '2人超過ペナルティ (07:00-20:00)'},
        {'name': 'penalty_surplus_3_plus_07_20', 'category': '人員の過不足', 'description_jp': '3人以上超過ペナルティ (07:00-20:00)'},

        {'name': 'no_staff_variance_20_24', 'category': '人員の過不足', 'description_jp': '過不足を完全に禁止 (20:00-24:00)'},
        {'name': 'penalty_shortage_20_24', 'category': '人員の過不足', 'description_jp': '人員不足ペナルティ (20:00-24:00)'},
        {'name': 'penalty_surplus_1_20_24', 'category': '人員の過不足', 'description_jp': '1人超過ペナルティ (20:00-24:00)'},
        {'name': 'penalty_surplus_2_20_24', 'category': '人員の過不足', 'description_jp': '2人超過ペナルティ (20:00-24:00)'},
        {'name': 'penalty_surplus_3_plus_20_24', 'category': '人員の過不足', 'description_jp': '3人以上超過ペナルティ (20:00-24:00)'},

        {'name': 'no_staff_variance_24_07', 'category': '人員の過不足', 'description_jp': '過不足を完全に禁止 (24:00-翌07:00)'},
        {'name': 'penalty_shortage_24_07', 'category': '人員の過不足', 'description_jp': '人員不足ペナルティ (24:00-翌07:00)'},
        {'name': 'penalty_surplus_1_24_07', 'category': '人員の過不足', 'description_jp': '1人超過ペナルティ (24:00-翌07:00)'},
        {'name': 'penalty_surplus_2_24_07', 'category': '人員の過不足', 'description_jp': '2人超過ペナルティ (24:00-翌07:00)'},
        {'name': 'penalty_surplus_3_plus_24_07', 'category': '人員の過不足', 'description_jp': '3人以上超過ペナルティ (24:00-翌07:00)'},

        # 役職・スキル
        {'name': 'avoid_leader_and_support_same_day', 'category': '役職・スキル', 'description_jp': '責任者とサポの同日勤務回避'},
        {'name': 'ensure_full_time_early_day_shift', 'category': '役職・スキル', 'description_jp': '正職員の早番/日勤確保'},
    ]




    if request.method == 'POST':
        if 'submit_constraints' in request.form:
            try:
                all_constraints = ShiftConstraint.query.all()
                for constraint in all_constraints:
                    # Update constraint type
                    constraint_type_str = request.form.get(f'constraint_type_{constraint.id}')
                    if constraint_type_str in [ct.name for ct in ConstraintType]:
                        constraint.constraint_type = ConstraintType[constraint_type_str]

                    # Update value
                    value_str = request.form.get(f'value_{constraint.id}')
                    if value_str and value_str.isdigit():
                        constraint.value = int(value_str)
                    elif value_str == '':
                        constraint.value = None

                    # Update penalty
                    penalty_str = request.form.get(f'penalty_{constraint.id}')
                    if constraint.constraint_type == ConstraintType.SOFT:
                        if penalty_str and penalty_str.isdigit():
                            constraint.penalty = int(penalty_str)
                        else:
                            constraint.penalty = 0 # Default penalty if invalid or empty
                    else:
                        constraint.penalty = 0 # Non-soft constraints have no penalty

                db.session.commit()
                flash('制約条件を更新しました。', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'更新中にエラーが発生しました: {e}', 'danger')
            return redirect(url_for('admin.manage_constraints'))

        elif 'submit_special_day' in request.form:
            special_day_form = SpecialDayForm()
            if special_day_form.validate_on_submit():
                try:
                    special_day = SpecialDay(
                        date=special_day_form.date.data,
                        staff_increase=special_day_form.staff_increase.data,
                        description=special_day_form.description.data,
                        visit_time=special_day_form.visit_time.data or None
                    )
                    db.session.add(special_day)
                    db.session.commit()
                    flash(f"{special_day.date.strftime('%Y-%m-%d')}を特別日として設定しました。", "success")
                except Exception as e:
                    db.session.rollback()
                    flash(f"特別日の設定中にエラーが発生しました: {e}", "danger")
            return redirect(url_for("admin.manage_constraints"))

    special_day_form = SpecialDayForm()
    # DBにマスター制約が存在するか確認し、なければ作成・更新
    for mc in master_constraints:
        constraint = ShiftConstraint.query.filter_by(name=mc['name']).first()
        if not constraint:
            constraint = ShiftConstraint(
                name=mc['name'],
                constraint_type=ConstraintType.INACTIVE, # デフォルトは無効
                penalty=0
            )
            db.session.add(constraint)
        # カテゴリと説明は常にマスターリストで更新
        constraint.category = mc['category']
        constraint.description_jp = mc['description_jp']

    # 時間帯ごとの人員配置マスタ
    hourly_staffing_master = {
        '平日': [
            {'name': 'staffing_weekday_07_08', 'description_jp': '07:00-08:00', 'value': 4},
            {'name': 'staffing_weekday_08_09', 'description_jp': '08:00-09:00', 'value': 4},
            {'name': 'staffing_weekday_09_12', 'description_jp': '09:00-12:00', 'value': 3},
            {'name': 'staffing_weekday_12_13', 'description_jp': '12:00-13:00', 'value': 3},
            {'name': 'staffing_weekday_13_14', 'description_jp': '13:00-14:00', 'value': 2},
            {'name': 'staffing_weekday_14_16', 'description_jp': '14:00-16:00', 'value': 3},
            {'name': 'staffing_weekday_16_18', 'description_jp': '16:00-18:00', 'value': 3},
            {'name': 'staffing_weekday_18_19', 'description_jp': '18:00-19:00', 'value': 3},
            {'name': 'staffing_weekday_19_20', 'description_jp': '19:00-20:00', 'value': 3},
            {'name': 'staffing_weekday_20_23', 'description_jp': '20:00-23:00', 'value': 2},
            {'name': 'staffing_weekday_23_24', 'description_jp': '23:00-24:00', 'value': 2},
            {'name': 'staffing_weekday_24_07', 'description_jp': '24:00-翌7:00', 'value': 2},
        ],
        '休日': [
            {'name': 'staffing_holiday_07_08', 'description_jp': '07:00-08:00', 'value': 4},
            {'name': 'staffing_holiday_08_09', 'description_jp': '08:00-09:00', 'value': 4},
            {'name': 'staffing_holiday_09_12', 'description_jp': '09:00-12:00', 'value': 3},
            {'name': 'staffing_holiday_12_13', 'description_jp': '12:00-13:00', 'value': 4},
            {'name': 'staffing_holiday_13_14', 'description_jp': '13:00-14:00', 'value': 3},
            {'name': 'staffing_holiday_14_16', 'description_jp': '14:00-16:00', 'value': 4},
            {'name': 'staffing_holiday_16_18', 'description_jp': '16:00-18:00', 'value': 4},
            {'name': 'staffing_holiday_18_19', 'description_jp': '18:00-19:00', 'value': 4},
            {'name': 'staffing_holiday_19_20', 'description_jp': '19:00-20:00', 'value': 3},
            {'name': 'staffing_holiday_20_23', 'description_jp': '20:00-23:00', 'value': 2},
            {'name': 'staffing_holiday_23_24', 'description_jp': '23:00-24:00', 'value': 2},
            {'name': 'staffing_holiday_24_07', 'description_jp': '24:00-翌7:00', 'value': 2},
        ]
    }
    
    hourly_constraints = {'平日': [], '休日': []}
    for category, constraints in hourly_staffing_master.items():
        for hc in constraints:
            constraint = ShiftConstraint.query.filter_by(name=hc['name']).first()
            if not constraint:
                constraint = ShiftConstraint(
                    name=hc['name'],
                    description_jp=hc['description_jp'],
                    category='時間帯別人員配置', # 専用カテゴリ
                    value=hc['value'],
                    constraint_type=ConstraintType.HARD # これらは常にハード制約
                )
                db.session.add(constraint)
            hourly_constraints[category].append(constraint)

    db.session.commit()

    # 表示する制約をマスターリストにあるものだけに限定する
    master_constraint_names = [mc['name'] for mc in master_constraints]
    all_constraints = ShiftConstraint.query.filter(
        ShiftConstraint.name.in_(master_constraint_names)
    ).order_by(ShiftConstraint.category, ShiftConstraint.id).all()

    constraints_by_category = {}
    for constraint in all_constraints:
        if constraint.category not in constraints_by_category:
            constraints_by_category[constraint.category] = []
        constraints_by_category[constraint.category].append(constraint)
    
    # --- 特別日のリストを取得 ---
    special_days = SpecialDay.query.order_by(SpecialDay.date.asc()).all()

    return render_template(
        "admin/constraints.html",
        title="制約条件・特別日の編集",
        constraints_by_category=constraints_by_category,
        hourly_constraints=hourly_constraints,
        special_day_form=special_day_form,
        special_days=special_days,
        ConstraintType=ConstraintType # テンプレートでEnumを使えるように
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
    form = EmployeeForm(
        original_username=user.username,
        original_email=user.email,
        original_employee_number=user.employee_number,
        employment_type=user.employment_type
    )

    if form.validate_on_submit():
        try:
            user.username = form.username.data
            user.full_name = form.full_name.data
            user.employee_number = form.employee_number.data
            user.email = form.email.data or None
            user.employment_type = EmploymentType[form.employment_type.data]
            user.is_active = form.is_active.data
            user.max_consecutive_work_days = form.max_consecutive_work_days.data
            user.min_work_days = form.min_work_days.data
            user.max_work_days = form.max_work_days.data
            user.min_night_shifts = form.min_night_shifts.data
            user.max_night_shifts = form.max_night_shifts.data
            user.preferred_shift_1_id = form.preferred_shift_1.data
            user.preferred_shift_2_id = form.preferred_shift_2.data
            user.ng_shifts = ",".join(map(str, form.ng_shifts.data))
            
            if form.password.data:
                user.set_password(form.password.data)
            
            db.session.commit()
            flash(f"従業員「{user.full_name}」の情報を更新しました。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}", "danger")
        return redirect(url_for('admin.edit_employee', user_id=user_id))
        
    # バリデーションエラー時の処理
    if request.method == "POST" and form.errors:
        # 雇用形態に応じてシフト選択肢を再設定
        try:
            form.set_shift_choices_by_employment(EmploymentType[form.employment_type.data])
        except (KeyError, TypeError):
            pass
        # エラーメッセージをflashで表示
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", "danger")

    # GETリクエスト時のフォーム初期化
    if request.method == "GET":
        form.set_shift_choices_by_employment(user.employment_type)
        form.username.data = user.username
        form.full_name.data = user.full_name
        form.employee_number.data = user.employee_number
        form.email.data = user.email
        form.employment_type.data = user.employment_type.name
        form.is_active.data = user.is_active
        form.max_consecutive_work_days.data = user.max_consecutive_work_days
        form.min_work_days.data = user.min_work_days
        form.max_work_days.data = user.max_work_days
        form.min_night_shifts.data = user.min_night_shifts
        form.max_night_shifts.data = user.max_night_shifts
        form.preferred_shift_1.data = user.preferred_shift_1_id
        form.preferred_shift_2.data = user.preferred_shift_2_id
        if user.ng_shifts:
            allowed_shift_ids = {choice[0] for choice in form.ng_shifts.choices}
            current_ng_shift_ids = [int(shift_id) for shift_id in user.ng_shifts.split(',') if shift_id.strip()]
            form.ng_shifts.data = [shift_id for shift_id in current_ng_shift_ids if shift_id in allowed_shift_ids]
        else:
            form.ng_shifts.data = []

    return render_template(
        'admin/edit_employee.html', 
        title='従業員の編集', 
        form=form, 
        user=user
    )


@admin_bp.route("/delete_employee/<int:user_id>", methods=['POST'])
def delete_employee(user_id):
    """従業員を削除する"""
    user = db.get_or_404(User, user_id)
    try:
        # TODO: 関連するシフトデータなども削除、あるいは無効化する処理が必要か検討
        db.session.delete(user)
        db.session.commit()
        flash(f"従業員「{user.full_name}」を削除しました。", "success")
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


@admin_bp.route("/day_off/bulk_action", methods=['POST'])
def bulk_action_day_off():
    """選択された希望休申請を一括で処理する（承認・却下）"""
    request_ids = request.form.getlist('request_ids')
    status_filter = request.form.get('status_filter', 'pending')
    action = request.form.get('action') # 'approve' or 'reject'

    if not request_ids:
        flash('一括操作の対象となる申請が選択されていません。', 'warning')
        return redirect(url_for('admin.manage_day_off_requests', status=status_filter))

    if not action or action not in ['approve', 'reject']:
        flash('無効な操作です。', 'danger')
        return redirect(url_for('admin.manage_day_off_requests', status=status_filter))

    action_map = {
        'approve': {'new_status': 'approved', 'verb_jp': '承認'},
        'reject': {'new_status': 'rejected', 'verb_jp': '却下'}
    }
    new_status = action_map[action]['new_status']
    verb_jp = action_map[action]['verb_jp']

    try:
        # 現在のフィルタ（'pending' or 'approved'）に合致する申請のみを対象
        requests_to_update = DayOffRequest.query.filter(
            DayOffRequest.id.in_(request_ids),
            DayOffRequest.status == status_filter 
        ).all()
        
        updated_count = 0
        for req in requests_to_update:
            req.status = new_status
            updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            flash(f'{updated_count}件の希望休申請を一括で{verb_jp}しました。', 'success')
        else:
            flash(f'{verb_jp}対象の申請がありませんでした。', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f"一括処理中にエラーが発生しました: {e}", "danger")

    return redirect(url_for('admin.manage_day_off_requests', status=status_filter))


@admin_bp.route("/work_requests/bulk_action", methods=['POST'])
def bulk_action_work_request():
    """選択された希望勤務申請を一括で処理する（承認・却下）"""
    request_ids = request.form.getlist('request_ids')
    status_filter = request.form.get('status_filter', 'pending')
    action = request.form.get('action') # 'approve' or 'reject'

    if not request_ids:
        flash('一括操作の対象となる申請が選択されていません。', 'warning')
        return redirect(url_for('admin.manage_work_requests', status=status_filter))
        
    if not action or action not in ['approve', 'reject']:
        flash('無効な操作です。', 'danger')
        return redirect(url_for('admin.manage_work_requests', status=status_filter))

    action_map = {
        'approve': {'new_status': 'approved', 'verb_jp': '承認'},
        'reject': {'new_status': 'rejected', 'verb_jp': '却下'}
    }
    new_status = action_map[action]['new_status']
    verb_jp = action_map[action]['verb_jp']

    try:
        # 現在のフィルタ（'pending' or 'approved'）に合致する申請のみを対象
        requests_to_update = WorkRequest.query.filter(
            WorkRequest.id.in_(request_ids),
            WorkRequest.status == status_filter
        ).all()
        
        updated_count = 0
        for req in requests_to_update:
            req.status = new_status
            updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            flash(f'{updated_count}件の希望勤務申請を一括で{verb_jp}しました。', 'success')
        else:
            flash(f'{verb_jp}対象の申請がありませんでした。', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f"一括処理中にエラーが発生しました: {e}", "danger")

    return redirect(url_for('admin.manage_work_requests', status=status_filter))


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
    shift_names = ", ".join([st.name for st in req.shift_types])
    
    if action == 'approve':
        req.status = 'approved'
        flash(f'{req.user.username}さんの {req.date.strftime("%Y-%m-%d")} の希望勤務 ({shift_names}) を承認しました。', 'success')
    elif action == 'reject':
        req.status = 'rejected'
        flash(f'{req.user.username}さんの {req.date.strftime("%Y-%m-%d")} の希望勤務 ({shift_names}) を却下しました。', 'warning')
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


@admin_bp.route("/shifts-history", methods=["GET"])
def confirmed_shifts():
    """確定済みシフトの一覧を表示する"""
    
    # ShiftHistoryテーブルから年月でグループ化して確定済みシフトのリストを取得
    confirmed_shifts_info_query = db.session.query(
        func.extract('year', ShiftHistory.date).label('year'),
        func.extract('month', ShiftHistory.date).label('month')
    ).group_by('year', 'month').order_by(
        func.extract('year', ShiftHistory.date).desc(),
        func.extract('month', ShiftHistory.date).desc()
    )
    
    confirmed_shifts_raw = confirmed_shifts_info_query.all()

    confirmed_shifts_list = [
        {"year": int(year), "month": int(month)}
        for year, month in confirmed_shifts_raw
    ]

    return render_template(
        "admin/confirmed_shifts.html",
        title="確定済みシフト一覧",
        shifts_list=confirmed_shifts_list
    )

@admin_bp.route("/delete_confirmed_shift/<int:year>/<int:month>", methods=['POST'])
def delete_confirmed_shift(year, month):
    """指定された年月の確定済みシフトと関連データを削除する"""
    try:
        # 1. 該当する月のShiftHistoryレコードを削除
        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, calendar.monthrange(year, month)[1])
        
        ShiftHistory.query.filter(
            ShiftHistory.date >= start_date,
            ShiftHistory.date <= end_date
        ).delete(synchronize_session=False)

        # 2. 該当する月のShiftGenerationHistoryレコードを検索してPDFファイルを削除
        histories_to_delete = ShiftGenerationHistory.query.filter_by(
            target_year=year,
            target_month=month
        ).all()

        for history in histories_to_delete:
            db.session.delete(history)

        db.session.commit()
        flash(f"{year}年{month}月の確定済みシフトを削除しました。", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"削除中にエラーが発生しました: {e}", "danger")
        current_app.logger.error(f"Error deleting confirmed shift for {year}-{month}: {e}", exc_info=True)

    return redirect(url_for('admin.confirmed_shifts'))

@admin_bp.route("/download_excel/<int:year>/<int:month>")
def download_excel(year, month):
    """指定された年月の確定済みシフトをExcelファイルでダウンロードする"""
    try:
        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, calendar.monthrange(year, month)[1])

        # 当月のデータを取得
        current_month_shifts = ShiftHistory.query.filter(
            ShiftHistory.date.between(start_date, end_date)
        ).options(db.joinedload(ShiftHistory.user), db.joinedload(ShiftHistory.shift_type)).all()
        
        # 前月5日間のデータを取得
        prev_month_last_day = start_date - datetime.timedelta(days=1)
        prev_month_first_day_to_get = prev_month_last_day - datetime.timedelta(days=4)
        prev_month_shifts = ShiftHistory.query.filter(
            ShiftHistory.date.between(prev_month_first_day_to_get, prev_month_last_day)
        ).options(db.joinedload(ShiftHistory.user), db.joinedload(ShiftHistory.shift_type)).all()
        
        all_shifts = prev_month_shifts + current_month_shifts

        if not all_shifts:
            flash(f"{year}年{month}月の確定済みシフトデータがありません。", "warning")
            return redirect(url_for('admin.confirmed_shifts'))

        # 申請データを取得
        day_off_reqs, paid_leave_reqs, work_req_map = {}, {}, {}
        approved_day_offs = DayOffRequest.query.filter(
            DayOffRequest.date.between(start_date, end_date), DayOffRequest.status == "approved"
        ).all()
        for req in approved_day_offs:
            if req.request_type == 'paid_leave':
                paid_leave_reqs.setdefault(req.user_id, []).append(req.date)
            else:
                day_off_reqs.setdefault(req.user_id, []).append(req.date)

        approved_work_reqs = WorkRequest.query.filter(
            WorkRequest.date.between(start_date, end_date), WorkRequest.status == "approved"
        ).all()
        for req in approved_work_reqs:
            shift_names = [st.name for st in req.shift_types]
            if shift_names:
                work_req_map[(req.user_id, req.date)] = shift_names

        # 従業員リストを取得
        sort_order_employment = case(
            (User.employment_type == EmploymentType.MANAGER, 1),
            (User.employment_type == EmploymentType.SUPPORT, 2),
            (User.employment_type == EmploymentType.FULL_TIME, 3),
            (User.employment_type == EmploymentType.PART_TIME_8H, 4),
            (User.employment_type == EmploymentType.PART_TIME_SHORT, 5),
            else_=6
        )
        employees = User.query.filter_by(is_admin=False).order_by(
            User.employee_number.asc().nulls_last(),
            sort_order_employment,
            User.full_name
        ).all()

        # その他必要なデータを取得
        from collections import defaultdict
        generator = ShiftGenerator()
        generator._load_data_from_db()
        staffing_requirements = {c.name: c.value for c in ShiftConstraint.query.all()}
        
        prev_and_current_month_dates = [prev_month_first_day_to_get, end_date]
        special_days_query = SpecialDay.query.filter(
            SpecialDay.date.between(min(d.replace(day=1) for d in prev_and_current_month_dates), max(prev_and_current_month_dates))
        ).all()
        special_days = defaultdict(list)
        for day in special_days_query:
            special_days[day.date].append(day)

        # Excelを生成
        exporter = ExcelExporter()
        workbook = exporter.generate(
            year, month, employees, all_shifts,
            day_off_reqs=day_off_reqs,
            paid_leave_reqs=paid_leave_reqs,
            work_req_map=work_req_map,
            hourly_groups=generator.hourly_groups,
            staffing_requirements=staffing_requirements,
            special_days=special_days
        )
        
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        
        filename = f"shift_{year}_{month:02d}.xlsx"
        
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        flash(f"Excelファイルの生成中にエラーが発生しました: {e}", "danger")
        current_app.logger.error(f"Excel generation for {year}-{month} failed: {e}", exc_info=True)
        return redirect(url_for('admin.confirmed_shifts'))


@admin_bp.route("/download_generated_pdf/<int:year>/<int:month>")
def download_generated_pdf(year, month):
    """指定された年月の生成済みシフトをPDFファイルで動的に生成してダウンロードする"""
    try:
        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, calendar.monthrange(year, month)[1])

        # 当月のデータを取得 (ShiftAssignmentから)
        current_month_shifts_raw = ShiftAssignment.query.filter(
            ShiftAssignment.date.between(start_date, end_date)
        ).options(db.joinedload(ShiftAssignment.user), db.joinedload(ShiftAssignment.shift_type)).all()
        
        # 前月5日間のデータを取得 (ShiftHistoryから)
        prev_month_last_day = start_date - datetime.timedelta(days=1)
        prev_month_first_day_to_get = prev_month_last_day - datetime.timedelta(days=4)
        prev_month_shifts_raw = ShiftHistory.query.filter(
            ShiftHistory.date.between(prev_month_first_day_to_get, prev_month_last_day)
        ).options(db.joinedload(ShiftHistory.user), db.joinedload(ShiftHistory.shift_type)).all()

        if not current_month_shifts_raw:
            flash(f"{year}年{month}月の生成済みシフトデータがありません。", "warning")
            return redirect(url_for('admin.dashboard'))

        # PDF Exporterが期待する辞書のリスト形式に変換
        assignments = [
            {"date": s.date.isoformat(), "employee_id": s.user_id, "shift_type": s.shift_type.name}
            for s in prev_month_shifts_raw + current_month_shifts_raw
        ]

        # --- PDF生成に必要なデータを取得 (download_confirmed_pdfとほぼ同じ) ---
        sort_order_employment = case(
            (User.employment_type == EmploymentType.MANAGER, 1),
            (User.employment_type == EmploymentType.SUPPORT, 2),
            (User.employment_type == EmploymentType.FULL_TIME, 3),
            (User.employment_type == EmploymentType.PART_TIME_8H, 4),
            (User.employment_type == EmploymentType.PART_TIME_SHORT, 5),
            else_=6
        )
        # is_active=True のユーザーのみをPDFに含める
        all_users = User.query.filter_by(is_admin=False, is_active=True).order_by(
            User.employee_number.asc().nulls_last(),
            sort_order_employment,
            User.full_name
        ).all()
        employees_for_pdf = [{"id": u.id, "name": u.full_name} for u in all_users]

        all_shift_types = db.session.query(ShiftType).all()
        shift_types_map = {st.name: st for st in all_shift_types}
        
        day_off_reqs, paid_leave_reqs, work_req_map = {}, {}, {}
        approved_day_offs = DayOffRequest.query.filter(
            DayOffRequest.date.between(start_date, end_date), DayOffRequest.status == "approved"
        ).all()
        for req in approved_day_offs:
            if req.request_type == 'paid_leave':
                paid_leave_reqs.setdefault(req.user_id, []).append(req.date.isoformat())
            else:
                day_off_reqs.setdefault(req.user_id, []).append(req.date.isoformat())
        
        approved_work_reqs = WorkRequest.query.filter(
            WorkRequest.date.between(start_date, end_date), WorkRequest.status == "approved"
        ).all()
        for req in approved_work_reqs:
            shift_names = [st.name for st in req.shift_types]
            if shift_names:
                work_req_map[(req.user_id, req.date.isoformat())] = shift_names
        
        highlight_cells = set()
        for s in current_month_shifts_raw:
            date_str, user_id, shift_name = s.date.isoformat(), s.user_id, s.shift_type.name
            if date_str in day_off_reqs.get(user_id, []) and shift_name == "休":
                highlight_cells.add((user_id, date_str))
            elif date_str in paid_leave_reqs.get(user_id, []) and shift_name == "有":
                highlight_cells.add((user_id, date_str))
            if (user_id, date_str) in work_req_map and shift_name in work_req_map.get((user_id, date_str), []):
                highlight_cells.add((user_id, date_str))

        from collections import defaultdict
        generator = ShiftGenerator()
        generator._load_data_from_db()
        staffing_requirements = {c.name: c.value for c in ShiftConstraint.query.all()}
        
        special_days_query = SpecialDay.query.filter(
             db.or_(
                db.and_(db.extract('year', SpecialDay.date) == year, db.extract('month', SpecialDay.date) == month),
                db.and_(db.extract('year', SpecialDay.date) == prev_month_last_day.year, db.extract('month', SpecialDay.date) == prev_month_last_day.month)
            )
        ).all()
        special_days_map = defaultdict(list)
        for day in special_days_query:
            special_days_map[day.date.isoformat()].append(day)

        # PDFを生成
        pdf_exporter = PDFExporter()
        pdf_data = pdf_exporter.generate(
            year, month, employees_for_pdf, assignments,
            shift_types=shift_types_map, hourly_groups=generator.hourly_groups,
            highlight_cells=highlight_cells,
            staffing_requirements=staffing_requirements,
            special_days=special_days_map
        )
        
        filename = f"generated_shift_{year}_{month:02d}.pdf"
        
        return send_file(
            io.BytesIO(pdf_data),
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        flash(f"PDFファイルの生成中にエラーが発生しました: {e}", "danger")
        current_app.logger.error(f"PDF generation for {year}-{month} failed: {e}", exc_info=True)
        return redirect(url_for('admin.dashboard'))


@admin_bp.route("/download_pdf/<int:year>/<int:month>")
def download_confirmed_pdf(year, month):
    """指定された年月の確定済みシフトをPDFファイルで動的に生成してダウンロードする"""
    try:
        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, calendar.monthrange(year, month)[1])

        # 当月のデータを取得
        current_month_shifts_raw = ShiftHistory.query.filter(
            ShiftHistory.date.between(start_date, end_date)
        ).options(db.joinedload(ShiftHistory.user), db.joinedload(ShiftHistory.shift_type)).all()
        
        # 前月5日間のデータを取得
        prev_month_last_day = start_date - datetime.timedelta(days=1)
        prev_month_first_day_to_get = prev_month_last_day - datetime.timedelta(days=4)
        prev_month_shifts_raw = ShiftHistory.query.filter(
            ShiftHistory.date.between(prev_month_first_day_to_get, prev_month_last_day)
        ).options(db.joinedload(ShiftHistory.user), db.joinedload(ShiftHistory.shift_type)).all()

        if not current_month_shifts_raw and not prev_month_shifts_raw:
            flash(f"{year}年{month}月の確定済みシフトデータがありません。", "warning")
            return redirect(url_for('admin.confirmed_shifts'))

        # PDF Exporterが期待する辞書のリスト形式に変換
        assignments = [
            {"date": s.date.isoformat(), "employee_id": s.user_id, "shift_type": s.shift_type.name}
            for s in prev_month_shifts_raw + current_month_shifts_raw
        ]

        # --- PDF生成に必要なデータを取得 ---
        sort_order_employment = case(
            (User.employment_type == EmploymentType.MANAGER, 1),
            (User.employment_type == EmploymentType.SUPPORT, 2),
            (User.employment_type == EmploymentType.FULL_TIME, 3),
            (User.employment_type == EmploymentType.PART_TIME_8H, 4),
            (User.employment_type == EmploymentType.PART_TIME_SHORT, 5),
            else_=6
        )
        all_users = User.query.filter_by(is_admin=False).order_by(
            User.employee_number.asc().nulls_last(),
            sort_order_employment,
            User.full_name
        ).all()
        employees_for_pdf = [{"id": u.id, "name": u.full_name} for u in all_users]

        all_shift_types = db.session.query(ShiftType).all()
        shift_types_map = {st.name: st for st in all_shift_types}
        
        day_off_reqs, paid_leave_reqs, work_req_map = {}, {}, {}
        approved_day_offs = DayOffRequest.query.filter(
            DayOffRequest.date.between(start_date, end_date), DayOffRequest.status == "approved"
        ).all()
        for req in approved_day_offs:
            if req.request_type == 'paid_leave':
                paid_leave_reqs.setdefault(req.user_id, []).append(req.date.isoformat())
            else:
                day_off_reqs.setdefault(req.user_id, []).append(req.date.isoformat())
        
        approved_work_reqs = WorkRequest.query.filter(
            WorkRequest.date.between(start_date, end_date), WorkRequest.status == "approved"
        ).all()
        for req in approved_work_reqs:
            shift_names = [st.name for st in req.shift_types]
            if shift_names:
                work_req_map[(req.user_id, req.date.isoformat())] = shift_names
        
        highlight_cells = set()
        for s in current_month_shifts_raw:
            date_str, user_id, shift_name = s.date.isoformat(), s.user_id, s.shift_type.name
            if date_str in day_off_reqs.get(user_id, []) and shift_name == "休":
                highlight_cells.add((user_id, date_str))
            elif date_str in paid_leave_reqs.get(user_id, []) and shift_name == "有":
                highlight_cells.add((user_id, date_str))
            if (user_id, date_str) in work_req_map and shift_name in work_req_map.get((user_id, date_str), []):
                highlight_cells.add((user_id, date_str))

        generator = ShiftGenerator()
        generator._load_data_from_db()
        staffing_requirements = {c.name: c.value for c in ShiftConstraint.query.all()}
        
        prev_and_current_month_dates = [prev_month_first_day_to_get, end_date]
        special_days_query = SpecialDay.query.filter(
             db.or_(
                db.and_(db.extract('year', SpecialDay.date) == year, db.extract('month', SpecialDay.date) == month),
                db.and_(db.extract('year', SpecialDay.date) == prev_month_last_day.year, db.extract('month', SpecialDay.date) == prev_month_last_day.month)
            )
        ).all()
        special_days_map = defaultdict(list)
        for day in special_days_query:
            special_days_map[day.date.isoformat()].append(day)

        # PDFを生成
        pdf_exporter = PDFExporter()
        pdf_data = pdf_exporter.generate(
            year, month, employees_for_pdf, assignments,
            shift_types=shift_types_map, hourly_groups=generator.hourly_groups,
            highlight_cells=highlight_cells,
            staffing_requirements=staffing_requirements,
            special_days=special_days_map
        )
        
        filename = f"confirmed_shift_{year}_{month:02d}.pdf"
        
        return send_file(
            io.BytesIO(pdf_data),
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        flash(f"PDFファイルの生成中にエラーが発生しました: {e}", "danger")
        current_app.logger.error(f"PDF generation for {year}-{month} failed: {e}", exc_info=True)
        return redirect(url_for('admin.confirmed_shifts'))

