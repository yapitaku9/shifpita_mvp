import os
import logging
from datetime import datetime, timezone, timedelta
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


def to_jst(utc_dt):
    """Jinja2 filter to convert a naive UTC datetime to JST."""
    if utc_dt is None:
        return ""
    # Create a JST timezone object (UTC+9)
    jst = timezone(timedelta(hours=9), 'JST')
    # Assume the naive datetime is in UTC, make it timezone-aware, then convert to JST
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(jst)


def create_app(test_config=None) -> Flask:
    """アプリケーションファクトリ関数。"""
    logging.warning("--- Starting create_app ---")
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)
    logging.warning("--- Config loaded ---")

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # 拡張機能の初期化
    logging.warning("--- Initializing extensions ---")
    db.init_app(app)
    logging.warning("--- db initialized ---")
    migrate.init_app(app, db, render_as_batch=True)  # Add render_as_batch=True
    logging.warning("--- migrate initialized ---")
    login_manager.init_app(app)
    logging.warning("--- login_manager initialized ---")
    
    # Conditionally initialize Mail to prevent crash if not configured
    if app.config.get('MAIL_SERVER'):
        mail.init_app(app)
    logging.warning("--- mail initialized ---")


    # Register custom Jinja filter
    app.jinja_env.filters['jst'] = to_jst
    logging.warning("--- Jinja filter registered ---")

    # Blueprintの登録
    logging.warning("--- Registering blueprints ---")
    from app.views import main, admin, employee
    app.register_blueprint(main.bp)
    logging.warning("--- main blueprint registered ---")
    app.register_blueprint(admin.admin_bp)
    logging.warning("--- admin blueprint registered ---")
    app.register_blueprint(employee.employee_bp)
    logging.warning("--- employee blueprint registered ---")


    # Register commands
    from . import commands
    commands.init_app(app)
    logging.warning("--- Commands registered ---")

    # Ensure models are imported for Alembic autodetect
    from . import models
    logging.warning("--- Models imported ---")

    logging.warning("--- create_app finished ---")
    return app
