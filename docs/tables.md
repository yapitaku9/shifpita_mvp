# テーブル定義書

このドキュメントは、本アプリケーションのデータベースに使用される各テーブルの物理設計を定義します。

---

## 1. `roles` (役割マスタ)
従業員の役割を定義します。

| カラム名 | データ型 | PK | FK | Null | UQ | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | INTEGER | ✔ | | | | 主キー |
| `name` | VARCHAR(64) | | | | ✔ | 役割名 (例: `管理者`, `介護員`) |
| `can_night_shift`| BOOLEAN | | | | | 夜勤可否フラグ |
| `is_part_time` | BOOLEAN | | | | | パートタイマーフラグ |

---

## 2. `users` (ユーザー)
アプリケーションのログインユーザー。従業員と管理者の両方を含みます。

| カラム名 | データ型 | PK | FK | Null | UQ | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | INTEGER | ✔ | | | | 主キー |
| `username` | VARCHAR(64) | | | | ✔ | ログインID |
| `email` | VARCHAR(120) | | | ✔ | ✔ | メールアドレス |
| `password_hash` | VARCHAR(256) | | | | | ハッシュ化されたパスワード |
| `role_id` | INTEGER | | ✔ | | | `roles.id`への外部キー |

---

## 3. `shift_types` (シフトパターンマスタ)
勤務の種類を定義します。

| カラム名 | データ型 | PK | FK | Null | UQ | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | INTEGER | ✔ | | | | 主キー |
| `name` | VARCHAR(64) | | | | ✔ | シフト名 (例: `早1`, `夜1`) |
| `start_time` | TIME | | | | | 開始時刻 |
| `end_time` | TIME | | | | | 終了時刻 |

---

## 4. `day_off_requests` (希望休申請)
従業員からの希望休申請を記録します。

| カラム名 | データ型 | PK | FK | Null | UQ | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | INTEGER | ✔ | | | | 主キー |
| `request_date` | DATE | | | | | 希望休の日付 |
| `user_id` | INTEGER | | ✔ | | | `users.id`への外部キー |
| `created_at` | DATETIME | | | | | 申請日時 |

*複合ユニークキー: (`user_id`, `request_date`)*

---

## 5. `transactions` (シフト生成履歴)
シフト自動生成の実行履歴です。

| カラム名 | データ型 | PK | FK | Null | UQ | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | INTEGER | ✔ | | | | 主キー |
| `year` | INTEGER | | | | | 対象年 |
| `month` | INTEGER | | | | | 対象月 |
| `status` | VARCHAR(32) | | | | | 状態 (例: `success`, `failure`) |
| `created_at` | DATETIME | | | | | 生成実行日時 |

---

## 6. `shifts` (シフト)
生成されたシフトの一つ一つの割り当てを記録します。

| カラム名 | データ型 | PK | FK | Null | UQ | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | INTEGER | ✔ | | | | 主キー |
| `shift_date` | DATE | | | | | 勤務日 |
| `user_id` | INTEGER | | ✔ | | | `users.id`への外部キー |
| `shift_type_id` | INTEGER | | ✔ | | | `shift_types.id`への外部キー |
| `transaction_id`| INTEGER | | ✔ | | | `transactions.id`への外部キー |

*複合ユニークキー: (`user_id`, `shift_date`)*

---

## 7. `master` (マスター設定)
アプリケーション全体の固定設定値を管理します。

| カラム名 | データ型 | PK | FK | Null | UQ | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `key` | VARCHAR(64) | ✔ | | | | 設定キー (例: `max_consecutive_work_days`) |
| `value` | VARCHAR(256)| | | | | 設定値 |
| `description` | TEXT | | | ✔ | | 設定の説明 |
