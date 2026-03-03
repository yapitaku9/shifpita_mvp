from datetime import datetime
from app import db

class DesiredWorkDaysRequest(db.Model):
    """希望勤務日数申請モデル"""

    __tablename__ = "desired_work_days_requests"

    id = db.Column(db.Integer, primary_key=True)
    min_days = db.Column(db.Integer, nullable=False)
    max_days = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False) # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 外部キーとリレーションシップ
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User", back_populates="desired_work_days_requests")

    def __repr__(self):
        return f"<DesiredWorkDaysRequest {self.user.username} for {self.year}-{self.month}: {self.min_days}-{self.max_days} days>"
