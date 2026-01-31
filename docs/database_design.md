# データベース設計書

ShifPita MVPにおけるデータベースの詳細設計書です。
テーブル定義、インデックス、バリデーションルール、および初期データについて記述します。

---

## 1. テーブル定義 (Table Definitions)

### 1.1. マスタデータ (Master Data)

#### Role (役割マスタ)
従業員の役割（職種）を管理します。

| カラム名 | データ型 | NULL | デフォルト | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `role_id` | `INT` | No | - | **PK**, Auto Increment | 役割ID |
| `name` | `VARCHAR(50)` | No | - | Unique | 役割名 (例: 介護員, パート1) |
| `can_night_shift` | `BOOLEAN` | No | `FALSE` | - | 夜勤が可能かどうか |
| `monthly_work_days_rule` | `INT` | Yes | `NULL` | - | 月間の規定勤務日数 (NULL: 規定なし) |

#### ShiftType (シフト区分マスタ)
勤務の種類を管理します。

| カラム名 | データ型 | NULL | デフォルト | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `shift_type_id` | `INT` | No | - | **PK**, Auto Increment | シフト区分ID |
| `name` | `VARCHAR(20)` | No | - | Unique | シフト名 (例: 早1, 夜1, 休) |
| `start_time` | `TIME` | No | - | - | 勤務開始時刻 |
| `end_time` | `TIME` | No | - | - | 勤務終了時刻 |

#### ConstraintRule (制約ルールマスタ)
シフト作成時の制約条件を管理します。

| カラム名 | データ型 | NULL | デフォルト | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `rule_id` | `INT` | No | - | **PK**, Auto Increment | ルールID |
| `type` | `VARCHAR(20)` | No | - | Check('HARD', 'SOFT') | 制約の種類 |
| `parameters` | `JSON` | No | - | - | 制約パラメータ (必要人数等) |

### 1.2. トランザクションデータ (Transaction Data)

#### ShiftContext (シフト作成コンテキスト)
1回のシフト作成単位（対象月）を管理します。

| カラム名 | データ型 | NULL | デフォルト | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `context_id` | `INT` | No | - | **PK**, Auto Increment | コンテキストID |
| `year` | `INT` | No | - | - | 対象年 (例: 2026) |
| `month` | `INT` | No | - | - | 対象月 (例: 10) |
| `created_at` | `DATETIME` | No | `CURRENT_TIMESTAMP` | - | 作成日時 |

#### Employee (従業員)
その月のシフト作成対象となる従業員リスト。

| カラム名 | データ型 | NULL | デフォルト | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `employee_id` | `INT` | No | - | **PK**, Auto Increment | 従業員ID |
| `context_id` | `INT` | No | - | **FK** (ShiftContext) | 所属コンテキスト |
| `role_id` | `INT` | No | - | **FK** (Role) | 役割 |
| `name` | `VARCHAR(100)` | No | - | - | 従業員氏名 |

#### DayOffRequest (希望休)
従業員ごとの休日希望日。

| カラム名 | データ型 | NULL | デフォルト | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `request_id` | `INT` | No | - | **PK**, Auto Increment | 希望休ID |
| `employee_id` | `INT` | No | - | **FK** (Employee) | 対象従業員 |
| `date` | `DATE` | No | - | - | 希望する日付 |

#### SpecialDay (特別日)
通院日など、通常とは異なる人員配置が必要な日。

| カラム名 | データ型 | NULL | デフォルト | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `special_day_id` | `INT` | No | - | **PK**, Auto Increment | 特別日ID |
| `context_id` | `INT` | No | - | **FK** (ShiftContext) | 所属コンテキスト |
| `date` | `DATE` | No | - | - | 対象日付 |
| `additional_staff_count` | `INT` | No | `0` | - | 追加必要人数 |

#### ShiftAssignment (シフト割当結果)
自動生成されたシフトの確定データ。

| カラム名 | データ型 | NULL | デフォルト | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `assignment_id` | `INT` | No | - | **PK**, Auto Increment | 割当ID |
| `context_id` | `INT` | No | - | **FK** (ShiftContext) | 所属コンテキスト |
| `employee_id` | `INT` | No | - | **FK** (Employee) | 対象従業員 |
| `shift_type_id` | `INT` | No | - | **FK** (ShiftType) | シフト区分 |
| `date` | `DATE` | No | - | - | 対象日付 |

---

## 2. インデックス一覧 (Indexes)

パフォーマンスとデータ整合性を確保するためのインデックス定義です。

| テーブル名 | インデックス名 | カラム (複合) | 種類 | 目的 |
| :--- | :--- | :--- | :--- | :--- |
| `Role` | `idx_role_name` | `name` | UNIQUE | 役割名の重複防止 |
| `ShiftType` | `idx_shifttype_name` | `name` | UNIQUE | シフト名の重複防止 |
| `Employee` | `idx_employee_context` | `context_id` | INDEX | コンテキストごとの従業員検索 |
| `DayOffRequest` | `idx_dayoff_employee_date` | `employee_id`, `date` | UNIQUE | 同一従業員の同日重複防止 |
| `SpecialDay` | `idx_specialday_context_date` | `context_id`, `date` | UNIQUE | 同一コンテキストの同日重複防止 |
| `ShiftAssignment` | `idx_assignment_employee_date` | `employee_id`, `date` | UNIQUE | 同一従業員の同日シフト重複防止 |
| `ShiftAssignment` | `idx_assignment_context` | `context_id` | INDEX | コンテキストごとのシフト一括取得 |

---

## 3. バリデーションルール (Validation Rules)

APIリクエストおよびデータ保存時に適用されるバリデーションルールです。

### 3.1. シフト生成リクエスト (POST /api/shifts/generate)

| フィールド | ルール | 説明 |
| :--- | :--- | :--- |
| `year` | `required`, `integer`, `min:2024` | 対象年は必須、2024年以降 |
| `month` | `required`, `integer`, `between:1,12` | 対象月は必須、1〜12 |
| `employees` | `required`, `array`, `min:1` | 従業員リストは必須 |
| `employees.*.name` | `required`, `string`, `max:100` | 従業員名は必須 |
| `employees.*.role_id` | `required`, `exists:roles,role_id` | 有効な役割IDを指定 |
| `employees.*.day_off_requests` | `array` | 希望休リスト（任意） |
| `employees.*.day_off_requests.*` | `date_format:Y-m-d` | 日付形式 |
| `special_days` | `array` | 特別日リスト（任意） |
| `special_days.*.date` | `required`, `date_format:Y-m-d` | 特別日の日付 |
| `special_days.*.additional_staff` | `required`, `integer`, `min:1` | 追加人数は1人以上 |

---

## 4. シーダーデータ (Seed Data)

アプリケーションの初期構築時に投入するマスタデータです。

### 4.1. Role (役割)

| role_id | name | can_night_shift | monthly_work_days_rule |
| :--- | :--- | :--- | :--- |
| 1 | 介護員 | TRUE | 21 |
| 2 | パート1 | TRUE | NULL |
| 3 | パート2 | FALSE | NULL |
| 4 | パート3 | FALSE | NULL |
| 5 | パート4 | FALSE | NULL |
| 6 | 責任者 | TRUE | NULL |
| 7 | サポート | TRUE | NULL |

### 4.2. ShiftType (シフト区分)

※時間は施設運用の目安であり、実際のロジックでは区分IDや名称が主に使用されます。

| shift_type_id | name | start_time | end_time | 備考 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 早1 | 07:00 | 16:00 | |
| 2 | 早2 | 07:30 | 16:30 | |
| 3 | 日1 | 09:00 | 18:00 | |
| 4 | 日2 | 09:30 | 18:30 | |
| 5 | 遅1 | 11:00 | 20:00 | |
| 6 | 遅2 | 11:30 | 20:30 | |
| 7 | 夜1 | 16:00 | 10:00 | 翌日10時まで |
| 8 | 夜2 | 17:00 | 11:00 | 翌日11時まで |
| 9 | 明 | 00:00 | 00:00 | 夜勤明け（勤務なし扱い） |
| 10 | 休 | 00:00 | 00:00 | 公休 |
| 11 | 1 | 08:00 | 12:00 | パート4専用パターン |
| 12 | 2 | 09:00 | 13:00 | パート4専用パターン |
| 13 | 3 | 10:00 | 14:00 | パート4専用パターン |
| 14 | 4 | 11:00 | 15:00 | パート4専用パターン |
| 15 | 5 | 12:00 | 16:00 | パート4専用パターン |
| 16 | 6 | 13:00 | 17:00 | パート4専用パターン |
| 17 | 7 | 14:00 | 18:00 | パート4専用パターン |
| 18 | 8 | 15:00 | 19:00 | パート4専用パターン |

### 4.3. ConstraintRule (制約ルール - 例)

※MVPではコード内にハードコーディングされる可能性がありますが、データ構造としての例です。

| rule_id | type | parameters (JSON) |
| :--- | :--- | :--- |
| 1 | HARD | `{"name": "min_staff_weekday", "7-16": 4, "16-20": 3, "20-7": 2}` |
| 2 | HARD | `{"name": "min_staff_sunday", "7-16": 4, "16-20": 4, "20-7": 2}` |
| 3 | HARD | `{"name": "max_consecutive_days", "value": 5}` |
| 4 | HARD | `{"name": "max_consecutive_late_night", "value": 4}` |

### 4.4. テストデータ (ShiftContext - 例)

開発時の動作確認用データセットです。

**ShiftContext:**
- year: 2026
- month: 10

**Employee:**
- 佐藤 (介護員)
- 鈴木 (パート1)
- 高橋 (パート2)
- 田中 (パート4)

**DayOffRequest:**
- 佐藤: 2026-10-01, 2026-10-15
- 鈴木: 2026-10-05

**SpecialDay:**
- 2026-10-20 (追加人数: 1)