import os
from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()

login_manager.login_view = 'main.login'  # ログインが必要なページにアクセスした際の遷移先
login_manager.login_message = "このページにアクセスするにはログインが必要です。"


def create_app(test_config=None) -> Flask:
    """アプリケーションファクトリ関数。"""
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # 拡張機能の初期化
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    # Blueprintの登録
    from app.views import main, admin, employee
    app.register_blueprint(main.bp)
    app.register_blueprint(admin.admin_bp)
    app.register_blueprint(employee.employee_bp)

    return app
