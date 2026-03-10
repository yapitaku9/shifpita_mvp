import os
import time
import sqlalchemy
from dotenv import load_dotenv

print("Starting DB wait script...")

# .envファイルから環境変数を読み込む（ローカル実行用）
load_dotenv()

# RenderではDATABASE_URLは環境に直接設定されている
db_url = os.environ.get("DATABASE_URL")

if not db_url:
    print("DATABASE_URL not found. Exiting.")
    exit(1)

# Renderから提供されるDATABASE_URLは 'postgres://' で始まるため、
# SQLAlchemyが認識する 'postgresql://' に置換する
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# 接続先情報をログに出力（パスワードなどは表示しない）
if '@' in db_url:
    print(f"Waiting for database at {db_url.split('@')[-1]}...")
else:
    print("Waiting for database...")


# データベースへの接続試行
engine = sqlalchemy.create_engine(db_url)

max_retries = 12
retries = 0
while retries < max_retries:
    try:
        # 接続を試みる
        with engine.connect() as connection:
            print("Database connection successful.")
            exit(0) # 成功したらスクリプトを終了
    except Exception as e:
        print(f"Connection failed (attempt {retries + 1}/{max_retries})...")
        retries += 1
        time.sleep(5) # 5秒待ってから再試行

print("Could not connect to the database after several retries. Exiting with error.")
exit(1) # 最終的に失敗したらエラーで終了
