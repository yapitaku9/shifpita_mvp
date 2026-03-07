import io
import calendar
import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont


class PDFExporter:
    """シフト表PDFを生成するクラス。"""

    def __init__(self):
        # 日本語フォントの登録
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
            self.font_name = "HeiseiKakuGo-W5"
        except Exception:
            self.font_name = "Helvetica"  # フォールバック

    def _is_shift_active_at(
        self, check_time: datetime.time, shift_start: datetime.time, shift_end: datetime.time
    ) -> bool:
        """指定した時刻にシフトが勤務時間内か判定する（日またぎ対応）"""
        if shift_start < shift_end:
            # 日中シフト
            return shift_start <= check_time < shift_end
        else:
            # 夜勤など日またぎシフト
            return check_time >= shift_start or check_time < shift_end

    def generate(
        self, year: int, month: int, employees: list, assignments: list, shift_types: dict, hourly_groups: dict, highlight_cells: set
    ) -> bytes:
        """PDFを生成してバイト列として返します。

        Args:
            year (int): 年
            month (int): 月
            employees (list): 従業員リスト [{'id': 1, 'name': '...'}, ...]
            assignments (list): シフト割当 [{'date': 'YYYY-MM-DD', 'employee_id': 1, 'shift_type': '早1'}, ...]
            shift_types (dict): キーがシフト名、値がShiftTypeオブジェクトの辞書
            hourly_groups (dict): キーが時間、値が(シフト名, オフセット)のタプルリストの辞書
            highlight_cells (set): 文字色を赤くするセルの(user_id, date)タプルのセット

        Returns:
            bytes: PDFファイルのバイナリデータ
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=18,
        )

        elements = []
        styles = getSampleStyleSheet()

        # タイトル
        title_style = styles["Title"]
        title_style.fontName = self.font_name
        elements.append(Paragraph(f"{year}年{month}月 勤務表", title_style))
        elements.append(Spacer(1, 20))

        # 日付ヘッダーの作成
        dates = sorted(list(set(a["date"] for a in assignments)))
        if not dates:
            last_day = calendar.monthrange(year, month)[1]
            dates = [f"{year}-{month:02d}-{d:02d}" for d in range(1, last_day + 1)]

        weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
        header_date_cells = []
        for d_str in dates:
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            wd = dt.weekday()
            day_part = d_str.split("-")[-1]
            header_date_cells.append(f"{day_part}\n({weekdays_ja[wd]})")

        header_row = ["氏名"] + header_date_cells + ["勤務日", "有給休暇", "総勤務日数", "休日", "夜勤日数"]
        data = [header_row]

        # --- 集計処理 ---
        assignment_map = {
            (a["employee_id"], a["date"]): a["shift_type"] for a in assignments
        }

        # ハード制約で定義されているチェック時刻
        constraint_hours = [7, 8, 9, 12, 13, 14, 16, 18, 19]
        summary_labels = {h: f"{h:02d}:00時点" for h in constraint_hours}
        summary_labels["night"] = "夜勤帯(20-7時)"

        # 従業員ごとの行を作成
        for emp in employees:
            work_days = 0
            paid_holidays = 0
            holidays = 0
            night_shifts = 0
            row_shifts = []

            for d in dates:
                shift_name = assignment_map.get((emp["id"], d), "")
                row_shifts.append(shift_name)

                # 新しい集計ロジック
                if shift_name and shift_name not in ["有", "休", "明"]:
                    work_days += 1
                if shift_name == "有":
                    paid_holidays += 1
                if shift_name in ["休", "明"]:
                    holidays += 1
                if "夜" in shift_name:
                    night_shifts += 1
            
            total_work_days = work_days + paid_holidays
            row = [emp["name"]] + row_shifts + [str(work_days), str(paid_holidays), str(total_work_days), str(holidays), str(night_shifts)]
            data.append(row)

        # --- 集計行の作成 (hourly_groups を参照する新ロジック) ---
        summary_counts = {
            label: {d: 0 for d in dates} for label in summary_labels.values()
        }
        date_to_idx = {d: i for i, d in enumerate(dates)}

        # hourly_groups を逆引きしやすいように変形: { shift_name: { hour: offset, ... }, ... }
        shift_to_hours_map = {}
        if hourly_groups:
            for hour, shifts_with_offset in hourly_groups.items():
                for s_name, offset in shifts_with_offset:
                    if s_name not in shift_to_hours_map:
                        shift_to_hours_map[s_name] = {}
                    shift_to_hours_map[s_name][hour] = offset

        for assignment in assignments:
            shift_name = assignment["shift_type"]

            # 「休」「明」「有」は勤務時間がない、または人員配置に含めないため、カウントから除外する
            if shift_name in ["休", "明", "有"]:
                continue

            d_str = assignment["date"]  # シフトが割り当てられた日

            # 夜勤帯ラベルのカウント (これは単純な名称ベースなので変更なし)
            if "夜" in shift_name:
                summary_counts[summary_labels["night"]][d_str] += 1

            if shift_name not in shift_to_hours_map:
                continue
            
            # このシフトが貢献する時間を hourly_groups から調べる
            hours_with_offset = shift_to_hours_map[shift_name]
            for hour, offset in hours_with_offset.items():
                if hour not in constraint_hours:  # PDFで表示する時間帯でなければスキップ
                    continue
                
                target_date_str = None
                if offset == 0:
                    # 当日勤務
                    target_date_str = d_str
                elif offset == 1:
                    # 翌日勤務
                    current_date_idx = date_to_idx.get(d_str)
                    if current_date_idx is not None and current_date_idx + 1 < len(dates):
                        target_date_str = dates[current_date_idx + 1]

                if target_date_str:
                    summary_counts[summary_labels[hour]][target_date_str] += 1

        summary_rows = []
        for label in sorted(summary_labels.values()):
            row = [label] + [str(summary_counts[label][d]) for d in dates] + ["", "", "", "", ""]
            summary_rows.append(row)
        data.extend(summary_rows)

        # テーブル作成
        page_width = landscape(A4)[0] - 60
        total_units = 2.5 + len(dates) + 5 # 5 summary columns
        unit_width = page_width / total_units
        col_widths = (
            [unit_width * 2.5]
            + [unit_width] * len(dates)
            + [unit_width] * 5
        )
        table = Table(data, colWidths=col_widths)

        # テーブルスタイル
        num_employees = len(employees)
        num_summary_rows = len(summary_rows)
        
        style_commands = [
            ("FONTNAME", (0, 0), (-1, -1), self.font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),  # Header
        ]

        # 集計行の背景色（エラー回避のため正数インデックスで指定）
        if num_summary_rows > 0:
            summary_start_row = 1 + num_employees
            style_commands.append(
                ("BACKGROUND", (0, summary_start_row), (-1, -1), colors.whitesmoke)
            )

        style = TableStyle(style_commands)

        # 曜日ごとのヘッダー色設定
        for i, d_str in enumerate(dates):
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            wd = dt.weekday()
            col_idx = i + 1
            if wd == 6:  # Sunday
                style.add("TEXTCOLOR", (col_idx, 0), (col_idx, 0), colors.red)
            elif wd == 5:  # Saturday
                style.add("TEXTCOLOR", (col_idx, 0), (col_idx, 0), colors.blue)

        # シフトタイプに応じた色付け
        num_employees = len(employees)
        for row_idx in range(1, num_employees + 1):
            user_id = employees[row_idx - 1]["id"]
            row_data = data[row_idx]
            for col_idx, cell_value in enumerate(row_data[1 : len(dates) + 1], start=1):
                date_str = dates[col_idx - 1]

                # 背景色の設定
                if cell_value in ["休", "明", "有"]:
                    style.add("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.pink)
                elif "夜" in cell_value:
                    style.add("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.lightyellow)

                # 希望が通った申請は文字色を赤にする
                if (user_id, date_str) in highlight_cells:
                    style.add("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.red)

        table.setStyle(style)
        elements.append(table)

        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
