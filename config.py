import os


class Config:
    """Flaskアプリケーションの基本設定クラス。"""

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-key-please-change"

    # データベース設定
    # SQLiteデータベースのファイル名
    DATABASE_FILE = "shifpita.db"

    # Flask設定
    # JSONレスポンスで日本語をASCIIエスケープせずに表示（文字化け防止）
    JSON_AS_ASCII = False
    # テンプレート変更時に自動リロード
    TEMPLATES_AUTO_RELOAD = True
