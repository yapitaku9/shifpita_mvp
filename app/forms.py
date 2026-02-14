from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, DateField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Regexp, Optional
from app.models.user import User
from app.models.master import Role
from app.models.day_off_request import DayOffRequest


class LoginForm(FlaskForm):
    """ログインフォーム"""
    username = StringField(
        "ユーザーID", 
        validators=[DataRequired(message="ユーザーIDは入力必須です。")]
    )
    password = PasswordField(
        "パスワード", 
        validators=[DataRequired(message="パスワードは入力必須です。")]
    )
    remember_me = BooleanField("ログイン状態を維持する")
    submit = SubmitField("ログイン")


class EmployeeForm(FlaskForm):
    """従業員登録・編集フォーム"""
    username = StringField(
        "ユーザーID (半角英数字6文字以上)",
        validators=[
            DataRequired(message="入力必須です。"),
            Length(min=6, message="6文字以上で入力してください。"),
            Regexp('^[A-Za-z0-9]+$', message='ユーザー名は半角英数字のみ使用できます。'),
        ]
    )
    email = StringField(
        "メールアドレス",
        validators=[Optional(), Email(message="有効なメールアドレスを入力してください。")]
    )
    # `coerce=int` は、フォームから送信された値を整数に変換する
    role = SelectField("役割", coerce=int, validators=[DataRequired(message="役割を選択してください。")])
    password = PasswordField(
        "パスワード (半角数字4文字)",
        validators=[
            DataRequired(message="入力必須です。"),
            Regexp('^[0-9]{4}$', message='パスワードは半角数字4文字で設定してください。')
        ]
    )
    submit = SubmitField("登録する")

    def __init__(self, *args, **kwargs):
        super(EmployeeForm, self).__init__(*args, **kwargs)
        # Roleテーブルから役割の選択肢を動的にセットする
        # (app_context内でないとDBクエリが実行できないので注意)
        from app import db
        self.role.choices = [(r.role_id, r.name) for r in db.session.query(Role).order_by('name').all()]

    def validate_username(self, username):
        """ユーザーIDのユニーク制約をチェック"""
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('このユーザーIDは既に使用されています。')

    def validate_email(self, email):
        """メールアドレスのユニーク制約をチェック"""
        # メールアドレスが入力されている場合のみチェック
        if email.data:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('このメールアドレスは既に使用されています。')


class DayOffRequestForm(FlaskForm):
    """希望休申請フォーム"""
    date = DateField("日付", validators=[DataRequired(message="日付を入力してください。")], format='%Y-%m-%d')
    submit = SubmitField("申請する")

    def validate_date(self, date):
        """同じ日付の申請が既にないかチェック"""
        from flask_login import current_user
        existing_request = DayOffRequest.query.filter_by(
            user_id=current_user.id, 
            date=date.data
        ).first()
        if existing_request:
            raise ValidationError('この日付の希望休は既に申請済みです。')
