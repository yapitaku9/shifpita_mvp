import enum
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager
from app.models.master import ShiftType

# ユーザーと勤務可能シフトの中間テーブル
user_workable_shifts = db.Table('user_workable_shifts',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('shift_type_id', db.Integer, db.ForeignKey('shift_types.shift_type_id'), primary_key=True)
)

class EmploymentType(enum.Enum):
    """雇用形態"""
    MANAGER = '責任者'
    SUPPORT = '責任者サポート'
    FULL_TIME = '介護員'
    PART_TIME_8H = 'パート８時間勤務'
    PART_TIME_SHORT = 'パート短時間勤務'
    HOSPITAL_VISIT_SUPPORT = '通院介助'


# 雇用形態別の選択可能シフト名
# 責任者・責任者サポート・介護員・パート８時間勤務: 10シフト
FULL_TIME_SHIFT_NAMES = ['早1', '早2', '日1', '日2', '遅1', '遅2', '夜1', '夜2', '明', '休']
# パート短時間勤務: 9シフト
SHORT_TIME_SHIFT_NAMES = ['1', '2', '3', '4', '5', '6', '7', '8', '休']
# 通院介助: 4シフト
HOSPITAL_VISIT_SHIFT_NAMES = ['通8', '通9', '休', '有']


def get_selectable_shift_choices(employment_type, include_blank=False, coerce_int=False, exclude_kyu=False):
    """
    雇用形態に応じた選択可能なシフトの選択肢を返す。
    返り値: [(shift_type_id, name), ...]
    coerce_int=True の場合は (int, name) のタプル。
    exclude_kyu=True の場合は「休」を除外（NG勤務用）。
    """
    if isinstance(employment_type, str):
        try:
            # Try to convert from enum member name string (e.g., 'PART_TIME_SHORT')
            employment_type = EmploymentType[employment_type]
        except KeyError:
            # Try to convert from enum member value string (e.g., 'パート短時間勤務')
            try:
                employment_type = EmploymentType(employment_type)
            except ValueError:
                return [] # Invalid string, return empty list

    if employment_type is None:
        return []

    selectable_shift_names = []
    if employment_type in [EmploymentType.MANAGER, EmploymentType.SUPPORT, EmploymentType.FULL_TIME, EmploymentType.PART_TIME_8H]:
        selectable_shift_names = FULL_TIME_SHIFT_NAMES.copy()
    elif employment_type == EmploymentType.PART_TIME_SHORT:
        selectable_shift_names = SHORT_TIME_SHIFT_NAMES.copy()
    elif employment_type == EmploymentType.HOSPITAL_VISIT_SUPPORT:
        selectable_shift_names = HOSPITAL_VISIT_SHIFT_NAMES.copy()

    if not selectable_shift_names:
        return []

    if exclude_kyu and '休' in selectable_shift_names:
        selectable_shift_names = [n for n in selectable_shift_names if n != '休']

    query = db.session.query(ShiftType.shift_type_id, ShiftType.name).filter(
        ShiftType.name.in_(selectable_shift_names)
    ).order_by(ShiftType.shift_type_id)

    if coerce_int:
        choices = [(tid, name) for tid, name in query.all()]
    else:
        choices = [(str(tid), name) for tid, name in query.all()]

    if include_blank:
        blank = ('', '---') if not coerce_int else (None, '---')
        return [blank] + choices
    return choices


class User(UserMixin, db.Model):
    """ユーザーアカウントモデル"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True) # ログインID
    full_name = db.Column(db.String(64), nullable=False) # 氏名
    employee_number = db.Column(db.Integer, unique=True, nullable=True, index=True) # 従業員番号
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False) # シフト生成対象
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 雇用形態
    employment_type = db.Column(db.Enum(EmploymentType), nullable=False, default=EmploymentType.FULL_TIME)
    
    # 希望・制約
    min_work_days = db.Column(db.Integer, nullable=True)  # 希望勤務日数（最小）
    max_work_days = db.Column(db.Integer, nullable=True)  # 希望勤務日数（最大）
    min_night_shifts = db.Column(db.Integer, nullable=True) # 夜勤日数（最小）
    max_night_shifts = db.Column(db.Integer, nullable=True) # 夜勤日数（最大）
    ng_shifts = db.Column(db.String(255), nullable=True) # NG勤務 (ShiftTypeのIDをカンマ区切りで保存)
    preferred_shift_1_id = db.Column(db.Integer, db.ForeignKey('shift_types.shift_type_id'), nullable=True)
    preferred_shift_2_id = db.Column(db.Integer, db.ForeignKey('shift_types.shift_type_id'), nullable=True)
    max_consecutive_work_days = db.Column(db.Integer, nullable=True, default=5) # 連勤制限

    preferred_shift_1 = db.relationship('ShiftType', foreign_keys=[preferred_shift_1_id])
    preferred_shift_2 = db.relationship('ShiftType', foreign_keys=[preferred_shift_2_id])

    day_off_requests = db.relationship(
        "DayOffRequest", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    work_requests = db.relationship(
        "WorkRequest", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    desired_work_days_requests = db.relationship(
        "DesiredWorkDaysRequest", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    workable_shifts = db.relationship(
        'ShiftType', secondary=user_workable_shifts,
        lazy='subquery',
        backref=db.backref('workers', lazy=True)
    )

    def set_password(self, password):
        """パスワードをハッシュ化して保存します。"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """提供されたパスワードがハッシュと一致するか検証します。"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.full_name}>"


@login_manager.user_loader
def load_user(user_id):
    """Flask-Loginがセッションからユーザーを読み込むために使用する関数。"""
    return db.session.get(User, int(user_id))
