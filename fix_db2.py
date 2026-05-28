import datetime
from app import create_app, db
from app.models.master import ShiftType

app = create_app()

REQUIRED_SHIFTS = [
    {'shift_type_id': 1, 'name': '早1', 'start_time': datetime.time(7, 0), 'end_time': datetime.time(16, 0)},
    {'shift_type_id': 2, 'name': '早2', 'start_time': datetime.time(8, 0), 'end_time': datetime.time(17, 0)},
    {'shift_type_id': 3, 'name': '日1', 'start_time': datetime.time(10, 0), 'end_time': datetime.time(19, 0)},
    {'shift_type_id': 4, 'name': '日2', 'start_time': datetime.time(11, 0), 'end_time': datetime.time(20, 0)},
    {'shift_type_id': 5, 'name': '遅1', 'start_time': datetime.time(14, 0), 'end_time': datetime.time(23, 0)},
    {'shift_type_id': 6, 'name': '遅2', 'start_time': datetime.time(15, 0), 'end_time': datetime.time(0, 0)},
    {'shift_type_id': 7, 'name': '夜1', 'start_time': datetime.time(23, 0), 'end_time': datetime.time(8, 0)},
    {'shift_type_id': 8, 'name': '夜2', 'start_time': datetime.time(0, 0), 'end_time': datetime.time(9, 0)},
    {'shift_type_id': 9, 'name': '明', 'start_time': None, 'end_time': None},
    {'shift_type_id': 10, 'name': '休', 'start_time': None, 'end_time': None},
    {'shift_type_id': 11, 'name': '1', 'start_time': datetime.time(7, 0), 'end_time': datetime.time(12, 0)},
    {'shift_type_id': 12, 'name': '2', 'start_time': datetime.time(7, 0), 'end_time': datetime.time(13, 0)},
    {'shift_type_id': 13, 'name': '3', 'start_time': datetime.time(8, 0), 'end_time': datetime.time(13, 0)},
    {'shift_type_id': 14, 'name': '4', 'start_time': datetime.time(8, 0), 'end_time': datetime.time(14, 0)},
    {'shift_type_id': 15, 'name': '5', 'start_time': datetime.time(8, 30), 'end_time': datetime.time(13, 30)},
    {'shift_type_id': 16, 'name': '6', 'start_time': datetime.time(9, 0), 'end_time': datetime.time(14, 0)},
    {'shift_type_id': 17, 'name': '7', 'start_time': datetime.time(9, 0), 'end_time': datetime.time(15, 0)},
    {'shift_type_id': 18, 'name': '8', 'start_time': datetime.time(13, 0), 'end_time': datetime.time(19, 0)},
]

with app.app_context():
    # Execute raw SQL to avoid ORM issues and just upsert
    db.session.execute(db.text("PRAGMA foreign_keys = OFF;"))
    db.session.execute(db.text("DELETE FROM shift_types;"))
    
    for req in REQUIRED_SHIFTS:
        st = req.get('start_time')
        et = req.get('end_time')
        # format times for sqlite
        st_str = st.strftime('%H:%M:%S.000000') if st else None
        et_str = et.strftime('%H:%M:%S.000000') if et else None
        
        db.session.execute(
            db.text("INSERT INTO shift_types (shift_type_id, name, start_time, end_time) VALUES (:id, :name, :st, :et)"),
            {"id": req['shift_type_id'], "name": req['name'], "st": st_str, "et": et_str}
        )
    db.session.commit()
    db.session.execute(db.text("PRAGMA foreign_keys = ON;"))
    print("Database overwritten with exactly the required shifts.")
