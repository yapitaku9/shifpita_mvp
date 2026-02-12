from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.forms import LoginForm, RegistrationForm
from app.models.user import User
from app.models.base import db


bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    return render_template("index.html", title="Home")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.get_or_none(User.user_id == form.user_id.data)
        if user is None or not user.check_password(form.password.data):
            flash("ユーザーIDまたはパスワードが無効です", "danger")
            return redirect(url_for("main.login"))
        login_user(user, remember=False)
        flash("ログインしました。", "success")
        return redirect(url_for("main.index"))
    return render_template("login.html", title="Log In", form=form, User=User)


@bp.route("/logout")
def logout():
    logout_user()
    flash("ログアウトしました。", "info")
    return redirect(url_for("main.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    # 既にユーザーが存在する場合は登録させない
    if User.select().count() > 0:
        flash("すでに管理者が登録されているため、新規登録はできません。", "warning")
        return redirect(url_for("main.login"))

    form = RegistrationForm()
    if form.validate_on_submit():
        with db.atomic():
            user = User(
                email=form.email.data or None,  # 空文字をNoneに変換
                user_id=form.user_id.data
            )
            user.set_password(form.password.data)
            user.save(force_insert=True)
        flash("ユーザー登録が完了しました。ログインしてください。", "success")
        return redirect(url_for("main.login"))
    return render_template("register.html", title="Register", form=form)
