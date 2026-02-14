from app import db
from datetime import datetime


class ShiftAssignment(db.Model):
    """日々のシフト割り当て結果を保存するモデル"""

    __tablename__ = "shift_assignments"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 外部キーとリレーションシップ
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    shift_type_id = db.Column(db.Integer, db.ForeignKey("shift_types.shift_type_id"), nullable=False)

    user = db.relationship("User", backref=db.backref("assignments", lazy="dynamic"))
    shift_type = db.relationship("ShiftType")

    def __repr__(self):
        return f"<ShiftAssignment {self.date} {self.user.username}: {self.shift_type.name}>"
