# gunicorn_config.py
import os

# アプリケーションのエントリポイントを run.py 内の app インスタンスに指定
wsgi_app = "run:app"

# サーバーソケット
# RenderやHerokuなどのホスティングプラットフォームはPORT環境変数を自動で設定します。
# ローカルでテストする場合は、デフォルトで8000番ポートを使用します。
port = os.environ.get("PORT", "8000")
bind = f"0.0.0.0:{port}"

# ワーカープロセスの数
# WEB_CONCURRENCY環境変数で指定されていなければ、デフォルトで3つのワーカーを使用します。
workers = int(os.environ.get("WEB_CONCURRENCY", 3))

# ロギング設定
# アクセスログとエラーログを標準出力に流すようにします。
accesslog = "-"
errorlog = "-"
loglevel = "info"

# タイムアウト設定（秒）
timeout = 120
