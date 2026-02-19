import click
from flask.cli import with_appcontext
from . import db
from .models.master import Role, ShiftType, ShiftConstraint
import datetime

@click.command('seed')
@with_appcontext
def seed_command():
    """Seeds the database with initial master data for production."""
    # Seed Roles
    if Role.query.first() is None:
        roles = [
            Role(name='責任者', can_night_shift=True, monthly_work_days_rule=21),
            Role(name='介護員', can_night_shift=True, monthly_work_days_rule=21),
            Role(name='パート1', can_night_shift=True),
            Role(name='パート2', can_night_shift=False),
            Role(name='パート3', can_night_shift=False),
            Role(name='パート4', can_night_shift=False),
            Role(name='サポート', can_night_shift=True),
        ]
        db.session.bulk_save_objects(roles)
        click.echo('Seeded roles.')
    else:
        click.echo('Roles already exist.')

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
        # NOTE: Add new constraints if they don't exist
        if not ShiftConstraint.query.filter_by(name='max_consecutive_late_night_shifts').first():
            db.session.add(ShiftConstraint(name='max_consecutive_late_night_shifts', value=4, description='遅番・夜勤の最大連続日数'))
            click.echo('Added max_consecutive_late_night_shifts constraint.')

        # NOTE: Update existing constraints if needed
        max_work_days = ShiftConstraint.query.filter_by(name='max_consecutive_work_days').first()
        if max_work_days and max_work_days.value != 5:
            max_work_days.value = 5
            click.echo('Updated max_consecutive_work_days to 5.')

    db.session.commit()

def init_app(app):
    """Register command with app."""
    app.cli.add_command(seed_command)
