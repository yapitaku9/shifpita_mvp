from peewee import SqliteDatabase, Model

# アプリケーションファクトリで初期化するためにNoneでインスタンス化
db = SqliteDatabase(None)


class BaseModel(Model):
    """全てのモデルの基底クラス。"""

    class Meta:
        database = db
