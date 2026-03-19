from app import db
import datetime

class ShiftGenerationHistory(db.Model):
    """シフト生成イベントの履歴を保存するモデル"""

    __tablename__ = 'shift_generation_history'

    id = db.Column(db.Integer, primary_key=True)
    generation_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    target_year = db.Column(db.Integer, nullable=False)
    target_month = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False)  # e.g., "Success", "Failed", "In Progress"
    
    def __repr__(self):
        return f'<ShiftGenerationHistory {self.id} for {self.target_year}-{self.target_month:02d} ({self.status})>'
