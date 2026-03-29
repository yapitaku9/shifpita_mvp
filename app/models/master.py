from app import db


import enum

class ShiftType(db.Model):
    """シフト区分マスタ"""

    __tablename__ = "shift_types"

    shift_type_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)

    def __repr__(self):
        return f"<ShiftType {self.name}>"

class ConstraintType(enum.Enum):
    HARD = 'ハード制約'
    SOFT = 'ソフト制約'
    INACTIVE = '無効'

class ShiftConstraint(db.Model):
    """シフト作成時の制約を管理するモデル"""

    __tablename__ = "shift_constraints"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) # 制約の内部名 (e.g., 'max_consecutive_work_days')
    value = db.Column(db.Integer, nullable=True) # 数値で設定する制約の値 (e.g., 5)
    description = db.Column(db.String(255), nullable=True) # 内部的な説明
    display_order = db.Column(db.Integer, nullable=False, server_default='0')

    # New columns for flexible constraints
    constraint_type = db.Column(db.Enum(ConstraintType), nullable=False, server_default='INACTIVE')
    penalty = db.Column(db.Integer, nullable=True) # ソフト制約の場合のペナルティ値
    category = db.Column(db.String(50), nullable=True) # UIでのグループ化用 (e.g., '連勤', '人員配置')
    description_jp = db.Column(db.String(255), nullable=True) # UI表示用の日本語説明


    def __repr__(self):
        return f"<ShiftConstraint {self.name}: {self.value}>"

