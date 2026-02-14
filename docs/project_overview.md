# ShifPita MVP プロジェクト概要

## 1. プロジェクト基本情報
- **アプリケーション名:** ShifPita MVP (シフピタ)
- **目的:** 
  特定施設の複雑な勤務条件に対応した勤務表を自動生成するWebアプリケーション。**管理者と従業員がそれぞれ専用のダッシュボードを持ち**、希望休の申請、シフト作成における制約条件の確認と編集からシフト作成、履歴の確認までを一貫してオンラインで管理できる環境を提供する。手動作成の負担を抜本的に解消し、従業員の公平性や希望を最大限に尊重した質の高い勤務表の作成を目指す。
- **フレームワーク:** Flask
- **データベース:** SQLite (開発環境)

## 2. 技術スタック

### バックエンド
- **Python:** 3.9+
- **Flask:** Webフレームワーク
- **Flask-SQLAlchemy:** ORM (Object-Relational Mapper)
- **Flask-Migrate:** データベースマイグレーション
- **Flask-Login:** ユーザー認証
- **Flask-WTF:** フォーム処理
- **Flask-Mail:** メール通知

### フロントエンド
- **Bootstrap:** 5.3
- **Vanilla JavaScript:** ES6+

## 3. ディレクトリ構造

FlaskのApplication FactoryパターンとBlueprintsを採用し、機能ごとにモジュールを分割した構成です。

```text
shifpita_mvp/
├── app/
│   ├── __init__.py          # Flaskアプリケーションファクトリ、拡張機能の初期化
│   ├── models/              # SQLAlchemyのモデル定義
│   │   ├── user.py
│   │   ├── shift.py
│   │   └── ...
│   ├── views/               # ルーティングとビュー関数 (Blueprints)
│   │   ├── main.py          # 共通・認証ルート
│   │   ├── admin.py         # 管理者用ルート
│   │   └── employee.py      # 従業員用ルート
│   ├── services/            # ビジネスロジック
│   │   ├── generator.py     # シフト自動生成エンジン
│   │   └── pdf_exporter.py  # PDF出力処理
│   ├── static/              # CSS, JavaScript, 画像などの静的ファイル
│   └── templates/           # Jinja2テンプレート
│       ├── base.html
│       ├── login.html
│       ├── admin/
│       └── employee/
├── migrations/              # Flask-Migrateのマイグレーションスクリプト
├── instance/                # インスタンス固有のデータ (DBファイルなど)
├── config.py                # 環境設定
├── run.py                   # 起動スクリプト
└── requirements.txt         # 依存ライブラリ一覧
```