from flask import render_template, flash, redirect, url_for, request, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlsplit
from app.forms import LoginForm
from app.models.user import User
from app import db

bp = Blueprint("main", __name__)


@bp.route("/")
@bp.route("/index")
@login_required
def index():
    """ログイン後のメインダッシュボード。ユーザーの役割に応じて表示を振り分ける。"""
    if current_user.is_admin:
        # TODO: 管理者用ダッシュボードのテンプレートをレンダリングする
        return render_template("admin_dashboard.html", title="管理者ダッシュボード")
    else:
        # TODO: 従業員用ダッシュボードのテンプレートをレンダリングする
        return render_template("employee_dashboard.html", title="従業員ダッシュボード")


@bp.route("/login", methods=["GET", "POST"])
def login():
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


@bp.route("/logout")
def logout():
    """ログアウト処理"""
    logout_user()
    flash("ログアウトしました。")
    return redirect(url_for("main.login"))
