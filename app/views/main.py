from flask import render_template, flash, redirect, url_for, request, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlsplit
from app.forms import LoginForm, RegistrationForm
from app.models.user import User
from app import db

bp = Blueprint("main", __name__)


@bp.route("/")
@bp.route("/index")
@login_required
def index():
    """ログイン後のメインページ。ユーザーの役割に応じて適切なダッシュボードにリダイレクトする。"""
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    else:
        return redirect(url_for("employee.dashboard"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    """ログインページ"""
    admin_exists = db.session.query(User).filter_by(is_admin=True).first() is not None

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

    return render_template(
        "login.html", title="ログイン", form=form, admin_exists=admin_exists
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    """管理者初回登録ページ"""
    if db.session.query(User).filter_by(is_admin=True).first():
        flash("既に管理者が登録されています")
        return render_template("register_admin.html", title="管理者アカウント作成", admin_exists=True)

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data, full_name=form.username.data, is_admin=True
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("管理者アカウントが作成されました。ログインしてください。")
        # 作成後、自動的にログインさせる
        login_user(user)
        return redirect(url_for("main.index"))

    return render_template(
        "register_admin.html", title="管理者アカウント作成", form=form, admin_exists=False
    )


@bp.route("/logout")
def logout():
    """ログアウト処理"""
    logout_user()
    flash("ログアウトしました。")
    return redirect(url_for("main.login"))
