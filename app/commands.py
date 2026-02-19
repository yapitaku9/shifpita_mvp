import click
from flask.cli import with_appcontext
from . import db
from .models.master import Role, ShiftType, ShiftConstraint
import datetime

@click.command('seed')
@with_appcontext
def seed_command():
    """Seeds the database with initial master data."""
    # Seed Roles
    if Role.query.first() is None:
        roles = [
            Role(name='admin', can_night_shift=True, monthly_work_days_rule=20),
            Role(name='full_time', can_night_shift=True, monthly_work_days_rule=20),
            Role(name='part_time', can_night_shift=False)
        ]
        db.session.bulk_save_objects(roles)
        click.echo('Seeded roles.')
    else:
        click.echo('Roles already exist.')

    # Seed ShiftTypes
    if ShiftType.query.first() is None:
        shift_types = [
            ShiftType(name='Day', start_time=datetime.time(9, 0), end_time=datetime.time(18, 0)),
            ShiftType(name='Night', start_time=datetime.time(17, 0), end_time=datetime.time(9, 0)),
            ShiftType(name='Holiday', start_time=datetime.time(0, 0), end_time=datetime.time(0, 0))
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
        ]
        db.session.bulk_save_objects(constraints)
        click.echo('Seeded shift constraints.')
    else:
        click.echo('Shift constraints already exist.')

    db.session.commit()

def init_app(app):
    """Register command with app."""
    app.cli.add_command(seed_command)
