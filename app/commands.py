import click
from flask.cli import with_appcontext
from . import db
from .models.master import ShiftType, ShiftConstraint
import datetime

@click.command('seed')
@with_appcontext
def seed_command():
    """Seeds the database with initial master data for production."""
    # Seed ShiftTypes
    if ShiftType.query.first() is None:
        shift_types = [
            ShiftType(name='早1', start_time=datetime.time(7, 0), end_time=datetime.time(16, 0)),
            ShiftType(name='早2', start_time=datetime.time(8, 0), end_time=datetime.time(17, 0)),
            ShiftType(name='日1', start_time=datetime.time(10, 0), end_time=datetime.time(19, 0)),
            ShiftType(name='日2', start_time=datetime.time(11, 0), end_time=datetime.time(20, 0)),
            ShiftType(name='遅1', start_time=datetime.time(14, 0), end_time=datetime.time(23, 0)),
            ShiftType(name='遅2', start_time=datetime.time(15, 0), end_time=datetime.time(0, 0)),
            ShiftType(name='夜1', start_time=datetime.time(23, 0), end_time=datetime.time(8, 0)),
            ShiftType(name='夜2', start_time=datetime.time(0, 0), end_time=datetime.time(9, 0)),
            ShiftType(name='明', start_time=datetime.time(0, 0), end_time=datetime.time(0, 0)),
            ShiftType(name='休', start_time=datetime.time(0, 0), end_time=datetime.time(0, 0)),
            ShiftType(name='1', start_time=datetime.time(7, 0), end_time=datetime.time(12, 0)),
            ShiftType(name='2', start_time=datetime.time(7, 0), end_time=datetime.time(13, 0)),
            ShiftType(name='3', start_time=datetime.time(8, 0), end_time=datetime.time(13, 0)),
            ShiftType(name='4', start_time=datetime.time(8, 0), end_time=datetime.time(14, 0)),
            ShiftType(name='5', start_time=datetime.time(8, 30), end_time=datetime.time(13, 30)),
            ShiftType(name='6', start_time=datetime.time(9, 0), end_time=datetime.time(14, 0)),
            ShiftType(name='7', start_time=datetime.time(9, 0), end_time=datetime.time(15, 0)),
            ShiftType(name='8', start_time=datetime.time(13, 0), end_time=datetime.time(19, 0)),
        ]
        db.session.bulk_save_objects(shift_types)
        click.echo('Seeded shift types.')
    else:
        click.echo('Shift types already exist.')

    # Seed ShiftConstraints
    if ShiftConstraint.query.first() is None:
        constraints = [
            ShiftConstraint(name='max_consecutive_work_days', value=5, description='最大連続勤務日数'),
            ShiftConstraint(name='min_consecutive_holidays', value=2, description='最低連続休日数'),
            ShiftConstraint(name='night_shift_interval_days', value=2, description='夜勤明けの最低連続休日数'),
            ShiftConstraint(name='max_consecutive_late_night_shifts', value=4, description='遅番・夜勤の最大連続日数'),
        ]
        db.session.bulk_save_objects(constraints)
        click.echo('Seeded shift constraints.')
    else:
        # --- データマイグレーションと新しい制約の追加 ---
        click.echo('Checking for new and obsolete constraints...')

        # 新しい時間帯別の人員配置制約の定義
        hourly_constraints = [
            # 7-9時
            {'name': 'min_staff_weekday_0700', 'value': 1, 'description': '【人員配置】平日 07:00-08:00', 'display_order': 10},
            {'name': 'min_staff_sunday_0700', 'value': 1, 'description': '【人員配置】休日 07:00-08:00', 'display_order': 11},
            {'name': 'min_staff_weekday_0800', 'value': 3, 'description': '【人員配置】平日 08:00-09:00', 'display_order': 12},
            {'name': 'min_staff_sunday_0800', 'value': 2, 'description': '【人員配置】休日 08:00-09:00', 'display_order': 13},
            {'name': 'min_staff_weekday_0900', 'value': 4, 'description': '【人員配置】平日 09:00-12:00', 'display_order': 14},
            {'name': 'min_staff_sunday_0900', 'value': 4, 'description': '【人員配置】休日 09:00-12:00', 'display_order': 15},
            # 12-19時
            {'name': 'min_staff_weekday_1200', 'value': 3, 'description': '【人員配置】平日 12:00-13:00', 'display_order': 20},
            {'name': 'min_staff_sunday_1200', 'value': 3, 'description': '【人員配置】休日 12:00-13:00', 'display_order': 21},
            {'name': 'min_staff_weekday_1300', 'value': 4, 'description': '【人員配置】平日 13:00-14:00', 'display_order': 22},
            {'name': 'min_staff_sunday_1300', 'value': 4, 'description': '【人員配置】休日 13:00-14:00', 'display_order': 23},
            {'name': 'min_staff_weekday_1400', 'value': 4, 'description': '【人員配置】平日 14:00-16:00', 'display_order': 24},
            {'name': 'min_staff_sunday_1400', 'value': 4, 'description': '【人員配置】休日 14:00-16:00', 'display_order': 25},
            {'name': 'min_staff_weekday_1600', 'value': 4, 'description': '【人員配置】平日 16:00-18:00', 'display_order': 26},
            {'name': 'min_staff_sunday_1600', 'value': 4, 'description': '【人員配置】休日 16:00-18:00', 'display_order': 27},
            {'name': 'min_staff_weekday_1800', 'value': 4, 'description': '【人員配置】平日 18:00-19:00', 'display_order': 28},
            {'name': 'min_staff_sunday_1800', 'value': 4, 'description': '【人員配置】休日 18:00-19:00', 'display_order': 29},
            {'name': 'min_staff_weekday_1900', 'value': 3, 'description': '【人員配置】平日 19:00-20:00', 'display_order': 30},
            {'name': 'min_staff_sunday_1900', 'value': 3, 'description': '【人員配置】休日 19:00-20:00', 'display_order': 31},
            # 20時以降（分割後）
            {'name': 'min_staff_weekday_2000_2300', 'value': 2, 'description': '【人員配置】平日 20:00-23:00', 'display_order': 40},
            {'name': 'min_staff_sunday_2000_2300', 'value': 2, 'description': '【人員配置】休日 20:00-23:00', 'display_order': 41},
            {'name': 'min_staff_weekday_2300_0000', 'value': 2, 'description': '【人員配置】平日 23:00-24:00', 'display_order': 42},
            {'name': 'min_staff_sunday_2300_0000', 'value': 2, 'description': '【人員配置】休日 23:00-24:00', 'display_order': 43},
            {'name': 'min_staff_weekday_0000_next_0700', 'value': 2, 'description': '【人員配置】平日 24:00-翌7:00', 'display_order': 44},
            {'name': 'min_staff_sunday_0000_next_0700', 'value': 2, 'description': '【人員配置】休日 24:00-翌7:00', 'display_order': 45},
        ]

        for c_data in hourly_constraints:
            if not ShiftConstraint.query.filter_by(name=c_data['name']).first():
                db.session.add(ShiftConstraint(**c_data))
                click.echo(f"Added constraint: {c_data['name']}")
        
        # 古い制約を削除
        old_constraints_to_delete = [
            'min_staff_weekday_2000_next_0700',
            'min_staff_sunday_2000_next_0700'
        ]
        for c_name in old_constraints_to_delete:
            constraint = ShiftConstraint.query.filter_by(name=c_name).first()
            if constraint:
                db.session.delete(constraint)
                click.echo(f"Deleted obsolete constraint: {c_name}")
        
        # その他の制約が存在しなければ追加
        other_constraints = [
            {'name': 'work_days_penalty', 'value': 100, 'description': '【ペナルティ】勤務日数の不足・超過', 'display_order': 200},
            {'name': 'night_shifts_penalty', 'value': 120, 'description': '【ペナルティ】夜勤日数の不足・超過', 'display_order': 201},
            {'name': 'weight_exceed_staffing_1', 'value': 10, 'description': '【ペナルティ】人員超過 (1人)', 'display_order': 210},
            {'name': 'weight_exceed_staffing_2', 'value': 30, 'description': '【ペナルティ】人員超過 (2人)', 'display_order': 211},
            {'name': 'weight_exceed_staffing_3_plus', 'value': 100, 'description': '【ペナルティ】人員超過 (3人以上)', 'display_order': 212},
            {'name': 'avoid_charge_and_support_same_day', 'value': 1, 'description': '【シフト構成】責任者とサポの同日勤務を回避', 'display_order': 300},
            {'name': 'ensure_main_staff_in_day_shift', 'value': 1, 'description': '【シフト構成】日中に正職員を1名以上配置', 'display_order': 301},
            {'name': 'require_day_off_after_ake', 'value': 1, 'description': '【シフト構成】「明け」の翌日は「休み」にする', 'display_order': 302},
        ]
        
        # シフト構成ルール
        shift_structure_rules = [
            {'name': 'disallow_specific_shifts_after_night', 'value': 1, 'description': '【シフト構成】夜勤の翌日に「遅・日・早」を禁止', 'display_order': 400},
            {'name': 'disallow_specific_shifts_after_late', 'value': 1, 'description': '【シフト構成】遅番の翌日に「日・早」を禁止', 'display_order': 401},
            {'name': 'disallow_specific_shifts_after_day', 'value': 1, 'description': '【シフト構成】日勤の翌日に「早」を禁止', 'display_order': 402},
        ]
        
        all_new_constraints = other_constraints + shift_structure_rules
        for c_data in all_new_constraints:
            if not ShiftConstraint.query.filter_by(name=c_data['name']).first():
                db.session.add(ShiftConstraint(**c_data))
                click.echo(f"Added constraint: {c_data['name']}")
                
        click.echo('Constraint check finished.')

    db.session.commit()


def init_app(app):
    """Register command with app."""
    app.cli.add_command(seed_command)
