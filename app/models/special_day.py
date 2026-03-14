from app import db
import datetime
from sqlalchemy import UniqueConstraint

class SpecialDay(db.Model):
    """
    特別日（通院日など）のモデル。
    この日に必要なスタッフ数を増やすなどの調整を行う。
    """
    __tablename__ = 'special_days'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    staff_increase = db.Column(db.Integer, nullable=False, default=1)
    description = db.Column(db.String(100), nullable=True)
    visit_time = db.Column(db.String(5), nullable=True) # e.g., "09:00"

    __table_args__ = (
        UniqueConstraint('date', 'visit_time', name='uq_special_days_date_visit_time'),
    )

    def __repr__(self):
        return f'<SpecialDay {self.date.strftime("%Y-%m-%d")}: {self.description}>'
