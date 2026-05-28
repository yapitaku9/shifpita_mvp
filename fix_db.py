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
    {'shift_type_id': 6, 'name': '遅2', 'start_time': datetime.time(15, 0), 'end_time': datetime.time(0, 0)}, # 24:00 -> 0:00
    {'shift_type_id': 7, 'name': '夜1', 'start_time': datetime.time(23, 0), 'end_time': datetime.time(8, 0)},
    {'shift_type_id': 8, 'name': '夜2', 'start_time': datetime.time(0, 0), 'end_time': datetime.time(9, 0)}, # 24:00 -> 0:00
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
    # Fetch all current shift types
    current_shifts = ShiftType.query.all()
    current_shift_names = {s.name: s for s in current_shifts}

    for req in REQUIRED_SHIFTS:
        if req['name'] in current_shift_names:
            # Update existing
            s = current_shift_names[req['name']]
            s.start_time = req['start_time']
            s.end_time = req['end_time']
            print(f"Updated {s.name}")
            del current_shift_names[req['name']]
        else:
            # Check if ID conflicts
            conflict = ShiftType.query.get(req['shift_type_id'])
            if conflict:
                print(f"ID Conflict for {req['shift_type_id']} ({conflict.name}). Updating to {req['name']}.")
                conflict.name = req['name']
                conflict.start_time = req['start_time']
                conflict.end_time = req['end_time']
                if conflict.name in current_shift_names:
                    del current_shift_names[conflict.name]
            else:
                s = ShiftType(
                    shift_type_id=req['shift_type_id'],
                    name=req['name'],
                    start_time=req['start_time'],
                    end_time=req['end_time']
                )
                db.session.add(s)
                print(f"Added {s.name}")
    
    # Optional: Delete shifts not in requirements, or just keep them?
    # The prompt says: "requirements.mdの勤務パターンをもとにデータベースを正しく修正してください。"
    # Let's delete the ones that are NOT in requirements (e.g. "通8", "通9", "有" etc.)
    # However, deleting might cause foreign key constraint failures if they are in use.
    # We will try to delete. If it fails, we rollback.
    try:
        for name, s in current_shift_names.items():
            print(f"Deleting unnecessary shift: {name}")
            db.session.delete(s)
        db.session.commit()
        print("Database updated successfully.")
    except Exception as e:
        db.session.rollback()
        print(f"Failed to delete some shift types due to constraint: {e}")
        db.session.commit() # Commit the additions/updates anyway
