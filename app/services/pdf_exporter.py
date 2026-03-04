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
        self, year: int, month: int, employees: list, assignments: list, shift_types: dict
    ) -> bytes:
        """PDFを生成してバイト列として返します。

        Args:
            year (int): 年
            month (int): 月
            employees (list): 従業員リスト [{'id': 1, 'name': '...'}, ...]
            assignments (list): シフト割当 [{'date': 'YYYY-MM-DD', 'employee_id': 1, 'shift_type': '早1'}, ...]
            shift_types (dict): キーがシフト名、値がShiftTypeオブジェクトの辞書

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

        header_row = ["氏名"] + header_date_cells + ["出勤日数", "夜勤回数"]
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
            work_days_count = 0
            night_shift_count = 0
            row_shifts = []

            for d in dates:
                shift_name = assignment_map.get((emp["id"], d), "")
                row_shifts.append(shift_name)

                # 勤務日数と夜勤回数のカウント
                if shift_name and shift_name not in ["休", "明"]:
                    work_days_count += 1
                if "夜" in shift_name:
                    night_shift_count += 1
            
            row = [emp["name"]] + row_shifts + [str(work_days_count), str(night_shift_count)]
            data.append(row)

        # --- 集計行の作成 ---
        # ハード制約で定義されているチェック時刻
        constraint_hours = [7, 8, 9, 12, 13, 14, 16, 18, 19]
        summary_labels = {h: f"{h:02d}:00時点" for h in constraint_hours}
        summary_labels["night"] = "夜勤帯(20-7時)"
        summary_counts = {
            label: {d: 0 for d in dates} for label in summary_labels.values()
        }

        # 日付文字列とインデックスのマッピング
        date_to_idx = {d: i for i, d in enumerate(dates)}

        for assignment in assignments:
            shift_name = assignment["shift_type"]
            shift_type = shift_types.get(shift_name)
            d_str = assignment["date"]

            # 「休」と「明」は勤務時間がないため、集計から除外する
            if shift_name in ["休", "明"]:
                continue
            
            if not shift_type or not shift_type.start_time or not shift_type.end_time:
                continue

            # 夜勤帯ラベルのカウント
            if "夜" in shift_name:
                summary_counts[summary_labels["night"]][d_str] += 1

            # 時間帯別の人員数カウント
            start_time = shift_type.start_time
            end_time = shift_type.end_time

            # 日またぎではないシフト (e.g., 07:00-16:00)
            if start_time < end_time:
                for hour in constraint_hours:
                    interval_start = datetime.time(hour, 0)
                    # constraint_hours は最大でも19なので、hour+1が24を超えることはない
                    interval_end = datetime.time(hour + 1, 0)
                    if start_time <= interval_start and end_time >= interval_end:
                        summary_counts[summary_labels[hour]][d_str] += 1
            # 日またぎシフト (e.g., 15:00-24:00 or 23:00-08:00)
            else:
                # 当日分のカウント
                end_time_today = datetime.time(23, 59, 59) # 便宜上の「今日の終わり」
                for hour in constraint_hours:
                    interval_start = datetime.time(hour, 0)
                    interval_end = datetime.time(hour + 1, 0)
                    # 今日の勤務時間帯 [start_time, 24:00) が [hour:00, hour+1:00) を含むか
                    if start_time <= interval_start and end_time_today >= interval_end:
                        summary_counts[summary_labels[hour]][d_str] += 1
                
                # 翌日分のカウント
                current_date_idx = date_to_idx.get(d_str)
                if current_date_idx is not None and current_date_idx + 1 < len(dates):
                    next_d_str = dates[current_date_idx + 1]
                    start_time_next_day = datetime.time(0, 0)
                    for hour in constraint_hours:
                        interval_start = datetime.time(hour, 0)
                        interval_end = datetime.time(hour + 1, 0)
                        # 翌日の勤務時間帯 [00:00, end_time) が [hour:00, hour+1:00) を含むか
                        if start_time_next_day <= interval_start and end_time >= interval_end:
                             summary_counts[summary_labels[hour]][next_d_str] += 1

        summary_rows = []
        for label in sorted(summary_labels.values()):
            row = [label] + [str(summary_counts[label][d]) for d in dates] + ["", ""]
            summary_rows.append(row)
        data.extend(summary_rows)

        # テーブル作成
        page_width = landscape(A4)[0] - 60
        total_units = 2.5 + len(dates) + 1.5 + 1.5
        unit_width = page_width / total_units
        col_widths = (
            [unit_width * 2.5]
            + [unit_width] * len(dates)
            + [unit_width * 1.5, unit_width * 1.5]
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
            row_data = data[row_idx]
            for col_idx, cell_value in enumerate(row_data[1 : len(dates) + 1], start=1):
                if "休" in cell_value:
                    style.add("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.red)
                elif "夜" in cell_value:
                    style.add("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.lightyellow)

        table.setStyle(style)
        elements.append(table)

        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
