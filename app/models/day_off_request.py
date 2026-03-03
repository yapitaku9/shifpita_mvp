from datetime import datetime
from app import db


class DayOffRequest(db.Model):
    """希望休申請モデル"""

    __tablename__ = "day_off_requests"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    # 申請タイプ ('day_off' (希望休), 'paid_leave' (有給休暇))
    request_type = db.Column(db.String(20), default="day_off", nullable=False)
    # ステータス (例: 'pending', 'approved', 'rejected')
    status = db.Column(db.String(20), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 外部キーとリレーションシップ
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User", back_populates="day_off_requests")

    def __repr__(self):
        return f"<DayOffRequest {self.user.username} on {self.date}>"
