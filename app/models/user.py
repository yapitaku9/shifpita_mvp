<<<<<<< HEAD
from peewee import CharField
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.models.base import BaseModel, db


class User(UserMixin, BaseModel):
    """シフト作成者のユーザー情報を管理するモデル。"""

    email = CharField(unique=True, null=True)
    user_id = CharField(unique=True, null=False)
    password_hash = CharField(null=False)

    class Meta:
        database = db
=======
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

class User(UserMixin, db.Model):
    """ユーザーアカウントモデル"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 外部キーとリレーションシップ
    role_id = db.Column(db.Integer, db.ForeignKey("roles.role_id"), nullable=True)
    desired_work_days = db.Column(db.Integer, nullable=True)  # パート用の希望勤務日数
    
    role = db.relationship("Role", back_populates="users")

    day_off_requests = db.relationship(
        "DayOffRequest", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    work_requests = db.relationship(
        "WorkRequest", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    workable_shifts = db.relationship(
        'ShiftType', secondary=user_workable_shifts,
        lazy='subquery',
        backref=db.backref('workers', lazy=True)
    )
>>>>>>> feature

    def set_password(self, password):
        """パスワードをハッシュ化して保存します。"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
<<<<<<< HEAD
        """入力されたパスワードが保存されているハッシュと一致するか確認します。"""
        return check_password_hash(self.password_hash, password)
=======
        """提供されたパスワードがハッシュと一致するか検証します。"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id):
    """Flask-Loginがセッションからユーザーを読み込むために使用する関数。"""
    return db.session.get(User, int(user_id))
>>>>>>> feature
