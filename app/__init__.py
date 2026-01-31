import os
from flask import Flask
from config import Config
from app.models.base import db


def create_app(test_config=None) -> Flask:
    """アプリケーションファクトリ関数。

    Args:
        test_config (dict, optional): テスト用の設定。デフォルトはNone。

    Returns:
        Flask: 作成されたFlaskアプリケーションインスタンス
    """
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # データベース初期化
    # インスタンスフォルダ内にDBファイルを作成
    db_path = os.path.join(app.instance_path, "shifpita.db")
    db.init(db_path, pragmas={"foreign_keys": 1})

    @app.before_request
    def before_request():
        if db.is_closed():
            db.connect()

    @app.teardown_request
    def _db_close(exc):
        if not db.is_closed():
            db.close()

    # Blueprintの登録
    from app.views import main, api

    app.register_blueprint(main.bp)
    app.register_blueprint(api.bp)

    return app
