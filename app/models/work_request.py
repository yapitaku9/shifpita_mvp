from datetime import datetime
from app import db


class WorkRequest(db.Model):
    """希望勤務申請モデル"""

    __tablename__ = "work_requests"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 外部キーとリレーションシップ
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    shift_type_id = db.Column(
        db.Integer, db.ForeignKey("shift_types.shift_type_id"), nullable=False
    )

    user = db.relationship("User", back_populates="work_requests")
    shift_type = db.relationship("ShiftType")

    def __repr__(self):
        return f"<WorkRequest {self.user.username} for {self.shift_type.name} on {self.date}>"
