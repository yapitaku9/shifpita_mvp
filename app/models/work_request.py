from datetime import datetime
from app import db


# 中間テーブル
work_request_shifts = db.Table(
    "work_request_shifts",
    db.Column(
        "work_request_id",
        db.Integer,
        db.ForeignKey("work_requests.id"),
        primary_key=True,
    ),
    db.Column(
        "shift_type_id",
        db.Integer,
        db.ForeignKey("shift_types.shift_type_id"),
        primary_key=True,
    ),
)


class WorkRequest(db.Model):
    """希望勤務申請モデル"""

    __tablename__ = "work_requests"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 外部キーとリレーションシップ
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User", back_populates="work_requests")
    shift_types = db.relationship(
        "ShiftType",
        secondary=work_request_shifts,
        lazy="subquery",  # subquery is often a good default for lazy loading
        backref=db.backref("work_requests", lazy=True),
    )

    def __repr__(self):
        shift_names = ", ".join([st.name for st in self.shift_types])
        return f"<WorkRequest {self.user.username} for [{shift_names}] on {self.date}>"
