from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, DateField, IntegerField, SelectMultipleField, widgets
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Regexp, Optional, NumberRange
from app.models.user import User, EmploymentType, get_selectable_shift_choices
from app.models.master import ShiftType
from app.models.day_off_request import DayOffRequest
from app.models.work_request import WorkRequest
import datetime


def safe_int_coerce(x):
    try:
        return int(x)
    except (ValueError, TypeError):
        return None


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
        "ログインID (半角英数字6文字以上)",
        validators=[
            DataRequired(message="入力必須です。"),
            Length(min=6, message="6文字以上で入力してください。"),
            Regexp('^[A-Za-z0-9]+$', message='ログインIDは半角英数字のみ使用できます。'),
        ]
    )
    full_name = StringField(
        "氏名",
        validators=[DataRequired(message="氏名は入力必須です。")]
    )
    email = StringField(
        "メールアドレス",
        validators=[Optional(), Email(message="有効なメールアドレスを入力してください。")]
    )
    employment_type = SelectField(
        "雇用形態",
        coerce=str,
        validators=[DataRequired(message="雇用形態を選択してください。")]
    )
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
    max_consecutive_work_days = IntegerField(
        "連勤制限（日数）",
        validators=[Optional(), NumberRange(min=1, max=31, message="1から31の範囲で入力してください。")]
    )
    preferred_shift_1 = SelectField(
        "優先シフト1",
        coerce=safe_int_coerce,
        validators=[Optional()],
    )
    preferred_shift_2 = SelectField(
        "優先シフト2",
        coerce=safe_int_coerce,
        validators=[Optional()],
    )
    min_work_days = IntegerField(
        "最低希望勤務日数",
        validators=[
            Optional(),
            NumberRange(min=0, max=31, message="0から31の範囲で入力してください。")
        ]
    )
    max_work_days = IntegerField(
        "最大希望勤務日数",
        validators=[
            Optional(),
            NumberRange(min=0, max=31, message="0から31の範囲で入力してください。")
        ]
    )
    min_night_shifts = IntegerField(
        "最低夜勤日数",
        validators=[
            Optional(),
            NumberRange(min=0, max=31, message="0から31の範囲で入力してください。")
        ]
    )
    max_night_shifts = IntegerField(
        "最大夜勤日数",
        validators=[
            Optional(),
            NumberRange(min=0, max=31, message="0から31の範囲で入力してください。")
        ]
    )
    ng_shifts = SelectMultipleField(
        "NG勤務",
        coerce=int,
        validators=[Optional()],
        widget=widgets.ListWidget(prefix_label=False),
        option_widget=widgets.CheckboxInput()
    )
    submit = SubmitField("登録する")

    def validate_max_work_days(self, max_work_days):
        if self.min_work_days.data is not None and max_work_days.data is not None:
            if self.min_work_days.data > max_work_days.data:
                raise ValidationError('最大日数は最低日数以上である必要があります。')

    def validate_max_night_shifts(self, max_night_shifts):
        if self.min_night_shifts.data is not None and max_night_shifts.data is not None:
            if self.min_night_shifts.data > max_night_shifts.data:
                raise ValidationError('最大夜勤日数は最低夜勤日数以上である必要があります。')

    def __init__(self, original_username=None, original_email=None, employment_type=None, *args, **kwargs):
        super(EmployeeForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email
        self._employment_type = employment_type

        self.employment_type.choices = [(e.name, e.value) for e in EmploymentType]
        self._update_shift_choices(employment_type or EmploymentType.FULL_TIME)

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

    def validate(self, extra_validators=None):
        """
        Overrides the default validation to perform data cleansing before the
        standard validators run.
        """
        # First, update choices based on the submitted employment_type.
        if self.employment_type.data:
            try:
                emp_type = EmploymentType[self.employment_type.data]
                self.set_shift_choices_by_employment(emp_type)
            except (KeyError, TypeError):
                pass

        # Second, cleanse the ng_shifts data based on the updated choices.
        if self.ng_shifts.data:
            allowed_ids = {choice[0] for choice in self.ng_shifts.choices}
            self.ng_shifts.data = [d for d in self.ng_shifts.data if d in allowed_ids]
        
        # Finally, call the parent's validate method.
        return super(EmployeeForm, self).validate(extra_validators)

    def _update_shift_choices(self, employment_type):
        """雇用形態に応じてNG勤務・優先シフトの選択肢を更新"""
        ng_choices = get_selectable_shift_choices(employment_type, exclude_kyu=True, coerce_int=True)
        pref_choices = get_selectable_shift_choices(employment_type, include_blank=True, coerce_int=True)
        self.ng_shifts.choices = ng_choices
        self.preferred_shift_1.choices = pref_choices
        self.preferred_shift_2.choices = pref_choices

    def set_shift_choices_by_employment(self, employment_type):
        """フォーム表示前に雇用形態に基づきシフト選択肢を更新（ビューから呼ぶ）"""
        if employment_type:
            if isinstance(employment_type, str):
                employment_type = EmploymentType[employment_type]
            self._update_shift_choices(employment_type)

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
    request_type = SelectField(
        "申請種別",
        choices=[('day_off', '希望休'), ('paid_leave', '有給休暇')],
        default='day_off',
        validators=[DataRequired(message="申請種別を選択してください。")]
    )
    dates = StringField("日付", validators=[DataRequired(message="日付を入力してください。")])
    submit = SubmitField("申請する")

    def validate_dates(self, dates):
        """同じ日付の希望休・希望勤務の申請が既にないかチェック"""
        from flask_login import current_user
        
        date_list_str = dates.data.split(', ')
        if not date_list_str or date_list_str == ['']:
            raise ValidationError('日付を選択してください。')

        for date_str in date_list_str:
            try:
                date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                raise ValidationError(f'無効な日付形式です: {date_str}')

            # 同じ日付の休み希望をチェック
            existing_day_off = DayOffRequest.query.filter_by(
                user_id=current_user.id, 
                date=date
            ).first()
            if existing_day_off:
                raise ValidationError(f'{date_str}の休み希望は既に申請済みです。')
                
            # 同じ日付の希望勤務をチェック
            existing_work_request = WorkRequest.query.filter_by(
                user_id=current_user.id,
                date=date
            ).first()
            if existing_work_request:
                raise ValidationError(f'{date_str}は希望勤務として既に申請済みです。休み希望は申請できません。')


class WorkRequestForm(FlaskForm):
    """希望勤務申請フォーム"""
    date = StringField("日付", validators=[DataRequired(message="日付を入力してください。")])
    shift_type_ids = SelectMultipleField(
        "希望勤務",
        coerce=int,
        validators=[DataRequired(message="希望勤務を1つ以上選択してください。")],
        widget=widgets.ListWidget(prefix_label=False),
        option_widget=widgets.CheckboxInput()
    )
    submit = SubmitField("申請する")

    def validate_date(self, date):
        """同じ日付の希望勤務・希望休の申請が既にないかチェック"""
        from flask_login import current_user

        try:
            date_obj = datetime.datetime.strptime(date.data, '%Y-%m-%d').date()
        except ValueError:
            raise ValidationError('無効な日付形式です。')

        # 同じ日付の希望勤務をチェック
        existing_work_request = WorkRequest.query.filter_by(
            user_id=current_user.id,
            date=date_obj
        ).first()
        if existing_work_request:
            raise ValidationError('この日付の希望勤務は既に申請済みです。')
            
        # 同じ日付の希望休をチェック
        existing_day_off = DayOffRequest.query.filter_by(
            user_id=current_user.id, 
            date=date_obj
        ).first()
        if existing_day_off:
            raise ValidationError('この日付は休み希望として既に申請済みです。希望勤務は申請できません。')


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


class ShiftConfirmationForm(FlaskForm):
    """シフト確定フォーム"""
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
    submit = SubmitField("この月のシフトを確定")


from wtforms import Form, HiddenField, FieldList, FormField


class SingleConstraintForm(Form):
    """単一の制約を編集するためのサブフォーム（CSRF無効）"""
    class Meta:
        csrf = False  # サブフォームではCSRFは不要
    
    name = HiddenField()
    description = StringField("説明", render_kw={'readonly': True})
    value = IntegerField(
        "値",
        validators=[
            DataRequired(message="値は必須です。"),
            NumberRange(min=0, message="0以上の数値を入力してください。")
        ]
    )
    is_boolean = HiddenField() # BooleanFieldとして扱うかのフラグ

class ShiftConstraintForm(FlaskForm):
    """制約のリストを管理するためのメインフォーム"""
    constraints = FieldList(FormField(SingleConstraintForm))
    submit_constraints = SubmitField("制約を更新する")


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


class UsernameChangeForm(FlaskForm):
    """ユーザー名変更フォーム"""
    username = StringField(
        "新しいユーザーID (半角英数字6文字以上)",
        validators=[
            DataRequired(message="入力必須です。"),
            Length(min=6, message="6文字以上で入力してください。"),
            Regexp('^[A-Za-z0-9]+$', message='ユーザー名は半角英数字のみ使用できます。'),
        ]
    )
    password = PasswordField(
        "現在のパスワード",
        validators=[DataRequired(message="変更を確定するには現在のパスワードが必要です。")]
    )
    submit = SubmitField("ユーザーIDを変更する")

    def __init__(self, original_username=None, *args, **kwargs):
        super(UsernameChangeForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user:
                raise ValidationError('このユーザーIDは既に使用されています。')


class SpecialDayForm(FlaskForm):
    """特別日設定フォーム"""
    date = DateField(
        "日付",
        validators=[DataRequired(message="日付は入力必須です。")],
        format='%Y-%m-%d'
    )
    staff_increase = IntegerField(
        "追加人員数",
        validators=[
            DataRequired(message="追加人員数は入力必須です。"),
            NumberRange(min=0, message="0以上の数値を入力してください。")
        ],
        default=1
    )
    description = StringField(
        "説明（例：通院日）",
        validators=[Optional(), Length(max=100)]
    )
    visit_time = SelectField(
        "通院時間",
        choices=[
            ('', '---'),
            ('08:00', '08:00'),
            ('09:00', '09:00')
        ],
        validators=[Optional()]
    )
    submit = SubmitField("特別日として設定")

    def validate_date(self, date):
        from app.models.special_day import SpecialDay
        existing_day = SpecialDay.query.filter_by(date=date.data).first()
        if existing_day:
            raise ValidationError('この日付は既に特別日として設定されています。')


class RegistrationForm(FlaskForm):
    """管理者初回登録フォーム"""
    username = StringField(
        "ユーザーID (半角英数字6文字以上)",
        validators=[
            DataRequired(message="入力必須です。"),
            Length(min=6, message="6文字以上で入力してください。"),
            Regexp('^[A-Za-z0-9]+$', message='ユーザー名は半角英数字のみ使用できます。'),
        ]
    )
    password = PasswordField(
        "パスワード",
        validators=[DataRequired(message="パスワードは入力必須です。")]
    )
    password2 = PasswordField(
        "パスワード（確認用）",
        validators=[
            DataRequired(message="確認用パスワードは入力必須です。"),
            EqualTo('password', message='パスワードが一致しません。')
        ]
    )
    submit = SubmitField("登録する")

    def validate_username(self, username):
        """ユーザーIDの重複チェック"""
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('このユーザーIDは既に使用されています。')

