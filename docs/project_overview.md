# プロジェクト基本情報

## 1. プロジェクト概要
- **プロジェクト名:** シフぴた（勤務表自動作成アプリ）
- **目的:** 勤務表の自動作成
- **フレームワーク:** Flask 3.0
- **データベース:** SQLite（開発環境）

## 2. 技術スタック

### バックエンド
- **Python:** 3.9以上
- **Flask:** 3.0.0
- **PeeWee:** 3.17.0 (ORM)
- **Flask-Login:** 0.6.3 (認証)
- **Flask-WTF:** 1.2.1 (フォーム)
- **Pillow:** 10.1.0 (画像処理)

### フロントエンド
- **Bootstrap:** 5.3
- **Font Awesome:** 6.x
- **Vanilla JavaScript:** ES6+

## 3. ディレクトリ構造 (推奨)

FlaskのApplication Factoryパターンを採用し、機能ごとにモジュールを分割した構成案です。

```text
shifpita_mvp/
├── app/
│   ├── __init__.py          # Flaskアプリケーションファクトリ・初期化処理
│   ├── models/              # データベースモデル (PeeWee)
│   │   ├── __init__.py
│   │   └── base.py          # DB接続設定・BaseModel定義
│   ├── views/               # ルーティング・ビュー関数 (Blueprints)
│   │   ├── __init__.py
│   │   ├── api.py           # APIエンドポイント (シフト生成・DL等)
│   │   └── main.py          # メイン画面・HTML配信
│   ├── services/            # ビジネスロジック
│   │   ├── __init__.py
│   │   └── generator.py     # シフト自動生成エンジン
│   ├── static/              # 静的ファイル
│   │   ├── css/
│   │   └── js/
│   └── templates/           # HTMLテンプレート (Jinja2)
│       └── index.html
├── instance/                # インスタンス固有データ (DBファイル等)
├── config.py                # 環境設定
├── run.py                   # 起動スクリプト
└── requirements.txt         # 依存ライブラリ一覧
```