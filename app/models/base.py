from peewee import Model, SqliteDatabase

# データベースインスタンス。create_app関数で初期化されます。
db = SqliteDatabase(None)


class BaseModel(Model):
    """すべてのモデルの基底クラス。"""

    class Meta:
        database = db
