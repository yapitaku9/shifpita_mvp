import os
from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from sqlalchemy import MetaData

# Add naming_convention for Alembic constraint auto-naming
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)
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
    migrate.init_app(app, db, render_as_batch=True)  # Add render_as_batch=True
    login_manager.init_app(app)
    mail.init_app(app)

    # Blueprintの登録
    from app.views import main, admin, employee
    app.register_blueprint(main.bp)
    app.register_blueprint(admin.admin_bp)
    app.register_blueprint(employee.employee_bp)

    # Register commands
    from . import commands
    commands.init_app(app)

    # Ensure models are imported for Alembic autodetect
    from . import models

    return app
