<<<<<<< HEAD
from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.forms import LoginForm, RegistrationForm
from app.models.user import User
from app.models.base import db

=======
from flask import render_template, flash, redirect, url_for, request, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlsplit
from app.forms import LoginForm
from app.models.user import User
from app import db
>>>>>>> feature

bp = Blueprint("main", __name__)


@bp.route("/")
<<<<<<< HEAD
@login_required
def index():
    return render_template("index.html", title="Home")
=======
@bp.route("/index")
@login_required
def index():
    """ログイン後のメインページ。ユーザーの役割に応じて適切なダッシュボードにリダイレクトする。"""
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    else:
        return redirect(url_for("employee.dashboard"))
>>>>>>> feature


@bp.route("/login", methods=["GET", "POST"])
def login():
<<<<<<< HEAD
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
=======
    """ログインページ"""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            db.select(User).where(User.username == form.username.data)
        )
        if user is None or not user.check_password(form.password.data):
            flash("ユーザーIDまたはパスワードが無効です")
            return redirect(url_for("main.login"))

        login_user(user, remember=form.remember_me.data)
        flash("ログインしました。")

        # リダイレクト先が安全か確認
        next_page = request.args.get("next")
        if not next_page or urlsplit(next_page).netloc != "":
            next_page = url_for("main.index")
        return redirect(next_page)

    return render_template("login.html", title="ログイン", form=form)
>>>>>>> feature


@bp.route("/logout")
def logout():
<<<<<<< HEAD
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
=======
    """ログアウト処理"""
    logout_user()
    flash("ログアウトしました。")
    return redirect(url_for("main.login"))
>>>>>>> feature
