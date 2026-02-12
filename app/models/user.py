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

    def set_password(self, password):
        """パスワードをハッシュ化して保存します。"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """入力されたパスワードが保存されているハッシュと一致するか確認します。"""
        return check_password_hash(self.password_hash, password)
