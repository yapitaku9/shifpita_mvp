from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Regexp, ValidationError, EqualTo, Optional
from app.models.user import User


class LoginForm(FlaskForm):
    """ログインフォーム。"""

    user_id = StringField(
        "ユーザーID",
        validators=[
            DataRequired("ユーザーIDは必須です。"),
            Length(min=6, message="ユーザーIDは6文字以上で入力してください。"),
            Regexp(r"^[a-zA-Z0-9]+$", message="ユーザーIDは半角英数字で入力してください。"),
        ],
    )
    password = PasswordField(
        "パスワード",
        validators=[
            DataRequired("パスワードは必須です。"),
            Regexp(r"^\d{4}$", message="パスワードは数字4桁で入力してください。"),
        ],
    )
    submit = SubmitField("ログイン")


class RegistrationForm(FlaskForm):
    """ユーザー登録フォーム。"""

    email = StringField(
        "メールアドレス",
        validators=[
            Optional(),
            Email("有効なメールアドレスを入力してください。"),
        ],
    )
    user_id = StringField(
        "ユーザーID",
        validators=[
            DataRequired("ユーザーIDは必須です。"),
            Length(min=6, message="ユーザーIDは6文字以上で入力してください。"),
            Regexp(r"^[a-zA-Z0-9]+$", message="ユーザーIDは半角英数字で入力してください。"),
        ],
    )
    password = PasswordField(
        "パスワード",
        validators=[
            DataRequired("パスワードは必須です。"),
            Regexp(r"^\d{4}$", message="パスワードは数字4桁で入力してください。"),
        ],
    )
    password2 = PasswordField(
        "パスワード（確認）",
        validators=[
            DataRequired("パスワード確認は必須です。"),
            EqualTo("password", message="パスワードが一致しません。"),
        ],
    )
    submit = SubmitField("登録")

    def validate_email(self, email):
        """メールアドレスの重複チェック。"""
        if email.data:
            user = User.get_or_none(User.email == email.data)
            if user is not None:
                raise ValidationError("そのメールアドレスはすでに登録されています。")

    def validate_user_id(self, user_id):
        """ユーザーIDの重複チェック。"""
        user = User.get_or_none(User.user_id == user_id.data)
        if user is not None:
            raise ValidationError("そのユーザーIDはすでに使用されています。")

    def validate(self, extra_validators=None):
        """フォーム全体のバリデーション。既存ユーザーがいないかチェック。"""
        # まず、フィールドレベルのバリデーションを実行します。
        initial_validation = super().validate(extra_validators)

        # フィールドレベルのバリデーションが失敗した場合、すぐにFalseを返します。
        if not initial_validation:
            return False

        # 管理者アカウントがすでに登録されているかチェックします。
        if User.select().count() > 0:
            raise ValidationError("すでに管理者アカウントが登録されています。新規登録はできません。")
        return True
