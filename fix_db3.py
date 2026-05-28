import datetime
from app import create_app, db
from app.models.master import ShiftType

app = create_app()

with app.app_context():
    db.session.execute(db.text("INSERT OR IGNORE INTO shift_types (shift_type_id, name, start_time, end_time) VALUES (19, '通8', '08:00:00.000000', '09:00:00.000000')"))
    db.session.execute(db.text("INSERT OR IGNORE INTO shift_types (shift_type_id, name, start_time, end_time) VALUES (20, '通9', '09:00:00.000000', '10:00:00.000000')"))
    db.session.execute(db.text("INSERT OR IGNORE INTO shift_types (shift_type_id, name, start_time, end_time) VALUES (21, '有', NULL, NULL)"))
    db.session.commit()
    print("Database updated with 通8, 通9, 有.")
