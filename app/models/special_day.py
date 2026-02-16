from app import db

class SpecialDay(db.Model):
    __tablename__ = 'special_days'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    staff_increase = db.Column(db.Integer, nullable=False, default=0)
    description = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f'<SpecialDay {self.date}: {self.description}>'
