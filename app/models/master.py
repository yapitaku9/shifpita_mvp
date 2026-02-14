from app import db


class Role(db.Model):
    """役割マスタ"""

    __tablename__ = "roles"

    role_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    can_night_shift = db.Column(db.Boolean, default=False, nullable=False)
    monthly_work_days_rule = db.Column(db.Integer, nullable=True)

    users = db.relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"


class ShiftType(db.Model):
    """シフト区分マスタ"""

    __tablename__ = "shift_types"

    shift_type_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    def __repr__(self):
        return f"<ShiftType {self.name}>"

# NOTE: ConstraintRule is not migrated for now to simplify the transition.
# It can be added later if needed.
