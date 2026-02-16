from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, DateField, IntegerField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Regexp, Optional, NumberRange
from app.models.user import User
from app.models.master import Role
from app.models.day_off_request import DayOffRequest
import datetime


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
    role = SelectField("役割", coerce=int, validators=[DataRequired(message="役割を選択してください。")])
    password = PasswordField(
        "新しいパスワード (半角数字4文字)",
        validators=[
            Optional(),
            Regexp('^[0-9]{4}$', message='パスワードは半角数字4文字で設定してください。')
        ]
    )
    password2 = PasswordField(
        "新しいパスワード（確認用）",
        validators=[
            Optional(),
            EqualTo('password', message='パスワードが一致しません。')
        ]
    )
    desired_work_days = IntegerField(
        "希望勤務日数（パートのみ）",
        validators=[Optional(), NumberRange(min=0, max=31, message="0から31の範囲で入力してください。")]
    )
    submit = SubmitField("登録する")

    def __init__(self, original_username=None, original_email=None, *args, **kwargs):
        super(EmployeeForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email
        
        from app import db
        self.role.choices = [(r.role_id, r.name) for r in db.session.query(Role).order_by('name').all()]

        # If it's an edit form, change the submit button text
        if original_username:
            self.submit.label.text = "更新する"
            # For editing, password is not required
            self.password.label.text = "新しいパスワード (変更する場合のみ入力)"
            self.password.validators = [
                Optional(),
                Regexp('^[0-9]{4}$', message='パスワードは半角数字4文字で設定してください。')
            ]
            self.password2.validators = [
                Optional(),
                EqualTo('password', message='パスワードが一致しません。')
            ]


    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user:
                raise ValidationError('このユーザーIDは既に使用されています。')

    def validate_email(self, email):
        if email.data and email.data != self.original_email:
            user = User.query.filter_by(email=self.email.data).first()
            if user:
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


class ShiftGenerationForm(FlaskForm):
    """シフト生成フォーム"""
    year = IntegerField(
        "年",
        validators=[DataRequired(), NumberRange(min=2024, max=2100)],
        default=datetime.date.today().year
    )
    month = IntegerField(
        "月",
        validators=[DataRequired(), NumberRange(min=1, max=12)],
        default=datetime.date.today().month
    )
    submit = SubmitField("シフトを生成")


def create_shift_constraint_form():
    """DBから制約を読み込み、動的にフォームクラスを生成するファクトリ関数"""
    from app.models.master import ShiftConstraint
    
    class DynamicShiftConstraintForm(FlaskForm):
        pass

    # DBからすべての制約を取得
    constraints = ShiftConstraint.query.order_by(ShiftConstraint.id).all()

    # 各制約に対してフォームフィールドを動的に追加
    for constraint in constraints:
        field = IntegerField(
            label=constraint.description,
            validators=[
                DataRequired(message=f"{constraint.description}は必須です。"),
                NumberRange(min=0, message="0以上の数値を入力してください。")
            ],
            default=constraint.value
        )
        setattr(DynamicShiftConstraintForm, constraint.name, field)

    # 最後にSubmitボタンを追加
    setattr(DynamicShiftConstraintForm, 'submit', SubmitField("更新する"))
    
    return DynamicShiftConstraintForm


class EmailEditForm(FlaskForm):
    """従業員用メールアドレス編集フォーム"""
    email = StringField(
        "新しいメールアドレス",
        validators=[DataRequired(message="入力必須です。"), Email(message="有効なメールアドレスを入力してください。")]
    )
    password = PasswordField(
        "現在のパスワード",
        validators=[DataRequired(message="変更を確定するには現在のパスワードが必要です。")]
    )
    submit = SubmitField("メールアドレスを変更する")

    def __init__(self, original_email=None, *args, **kwargs):
        super(EmailEditForm, self).__init__(*args, **kwargs)
        self.original_email = original_email

    def validate_email(self, email):
        if email.data and email.data != self.original_email:
            user = User.query.filter_by(email=self.email.data).first()
            if user:
                raise ValidationError('このメールアドレスは既に使用されています。')


class PasswordChangeForm(FlaskForm):
    """パスワード変更フォーム"""
    current_password = PasswordField(
        "現在のパスワード",
        validators=[DataRequired(message="現在のパスワードは入力必須です。")]
    )
    new_password = PasswordField(
        "新しいパスワード (半角数字4文字)",
        validators=[
            DataRequired(message="新しいパスワードは入力必須です。"),
            Regexp('^[0-9]{4}$', message='パスワードは半角数字4文字で設定してください。'),
        ]
    )
    new_password2 = PasswordField(
        "新しいパスワード（確認用）",
        validators=[
            DataRequired(message="確認用パスワードは入力必須です。"),
            EqualTo('new_password', message='新しいパスワードが一致しません。')
        ]
    )
    submit = SubmitField("パスワードを変更する")
