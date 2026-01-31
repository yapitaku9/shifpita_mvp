# 機能別画面・実装設計書

本ドキュメントでは、`screens.md` および `features.md` に基づき、アプリケーションの機能を画面（UI）とAPIの単位で整理し、実装に必要な情報をまとめます。

---

## 1. シフト作成・管理機能 (SPAメイン)

### 概要
アプリケーションのメインインターフェースです。SPA（Single Page Application）として実装され、ユーザーはページ遷移することなく、期間設定、従業員管理、希望休入力、シフト生成実行、結果確認の一連の操作を行います。

### ルーティング設計
- **GET** `/` (ルート名: `home`)
  - アプリケーションの初期ロードを行い、SPAのHTML/JSアセットを配信します。

### 必要なフォーム (UIコンポーネント)
- **期間設定フォーム:** 対象年月の選択
- **従業員管理フォーム:** 従業員の追加、削除、名前・役割の編集
- **カレンダー設定UI:** 日付クリックによる希望休のトグル、特別日（通院日など）の設定

### テンプレート
- `app/templates/index.html` (SPAのエントリーポイント)

### 実装ファイル一覧
- `app/views/main.py` (HTML配信用のビュー)
- `app/templates/index.html` (HTMLテンプレート)
- `app/static/js/main.js` (フロントエンドロジック)
- `app/static/css/style.css` (スタイルシート)

---

## 2. シフト自動生成機能 (API)

### 概要
フロントエンドから送信された従業員情報、役割、希望休、特別日などの条件を受け取り、バックエンドのロジック（制約充足問題ソルバー等）を用いて最適なシフトを計算し、結果をJSON形式で返却します。

### ルーティング設計
- **POST** `/api/shifts/generate` (ルート名: `api.shifts.generate`)

### 必要なフォーム (バリデーション)
- **GenerateShiftForm** (JSONリクエストボディ)
  - `year` (int): 対象年
  - `month` (int): 対象月
  - `employees` (list): 従業員リスト（名前、役割ID、希望休リスト含む）
  - `special_days` (list): 特別日設定リスト

### テンプレート
- なし (JSONレスポンス)

### 実装ファイル一覧
- `app/views/api.py` (APIエンドポイント定義)
- `app/services/generator.py` (シフト生成ロジック)
- `app/models/` (データ構造定義)

---

## 3. 結果出力機能 (API)

### 概要
生成・確定されたシフトデータを受け取り、印刷可能なPDFファイルを生成してダウンロードさせます。

### ルーティング設計
- **POST** `/api/shifts/download` (ルート名: `api.shifts.download`)

### 必要なフォーム (バリデーション)
- **DownloadShiftForm** (JSONリクエストボディ)
  - `year` (int): 対象年
  - `month` (int): 対象月
  - `assignments` (list): 確定したシフト割当データ

### テンプレート
- なし (PDFバイナリ返却)

### 実装ファイル一覧
- `app/views/api.py` (APIエンドポイント定義)
- `app/services/pdf_exporter.py` (PDF生成ロジック - Pillow/ReportLab等を使用)