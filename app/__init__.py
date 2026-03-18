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
    # Configure logging to see startup messages
    logging.basicConfig(level=logging.INFO)
    logging.info("--- Starting create_app ---")
    
    app = Flask(__name__, instance_relative_config=True)
    logging.info("--- Flask app created ---")

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)
    logging.info("--- Config loaded ---")

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    logging.info("--- Instance path checked ---")

    # 拡張機能の初期化
    logging.info("--- Initializing extensions ---")
    db.init_app(app)
    logging.info("--- db initialized ---")
    migrate.init_app(app, db, render_as_batch=True)
    logging.info("--- migrate initialized ---")
    login_manager.init_app(app)
    logging.info("--- login_manager initialized ---")
    
    # Conditionally initialize Mail to prevent crash if not configured
    if app.config.get('MAIL_SERVER'):
        mail.init_app(app)
    logging.info("--- mail initialized (conditional) ---")


    # Register custom Jinja filter
    app.jinja_env.filters['jst'] = to_jst
    logging.info("--- Jinja filter registered ---")

    # Blueprintの登録
    logging.info("--- Registering blueprints ---")
    from app.views import main, admin, employee
    logging.info("--- views imported ---")
    app.register_blueprint(main.bp)
    logging.info("--- main blueprint registered ---")
    app.register_blueprint(admin.admin_bp)
    logging.info("--- admin blueprint registered ---")
    app.register_blueprint(employee.employee_bp)
    logging.info("--- employee blueprint registered ---")


    # Register commands
    logging.info("--- Registering commands ---")
    from . import commands
    logging.info("--- commands imported ---")
    commands.init_app(app)
    logging.info("--- Commands registered ---")

    # Ensure models are imported for Alembic autodetect
    logging.info("--- Importing models ---")
    from . import models
    logging.info("--- Models imported ---")

    logging.info("--- create_app finished successfully ---")
    return app
