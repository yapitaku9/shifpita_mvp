import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# プロジェクトのベースディレクトリ
basedir = Path(__file__).resolve().parent


class Config:
    """Flaskアプリケーションの基本設定クラス。"""

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-key-please-change"

    # DATABASE_URLが設定されていればそれを使用し、なければローカルのSQLiteにフォールバック。
    # 一部のホスティング/DBプロバイダ(Render/Heroku/Neon等)は 'postgres://' 形式のURLを渡すが、
    # SQLAlchemy 1.4+ は 'postgresql://' しか認識しないため、ここで正規化する。
    _database_url = os.environ.get('DATABASE_URL')
    if _database_url and _database_url.startswith('postgres://'):
        _database_url = _database_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _database_url or \
        'sqlite:///' + str(Path(basedir) / 'instance' / 'shifpita.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask設定
    # JSONレスポンスで日本語をASCIIエスケープせずに表示（文字化け防止）
    JSON_AS_ASCII = False
    # テンプレート変更時に自動リロード
    TEMPLATES_AUTO_RELOAD = True

    # メール設定
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    # MAIL_PORTを安全に読み込む
    try:
        MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    except (ValueError, TypeError):
        MAIL_PORT = 25
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    ADMINS = ['your-admin-email@example.com'] # 管理者のメールアドレス
