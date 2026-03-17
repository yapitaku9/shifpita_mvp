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
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
            self.font_name = "HeiseiKakuGo-W5"
        except Exception:
            self.font_name = "Helvetica"

    def generate(
        self, year: int, month: int, employees: list, assignments: list, 
        shift_types: dict, hourly_groups: dict, highlight_cells: set,
        staffing_requirements: dict = None, special_days: dict = None
    ) -> bytes:
        """PDFを生成してバイト列として返します。"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30,
            topMargin=30, bottomMargin=18
        )
        elements = []
        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        title_style.fontName = self.font_name
        elements.append(Paragraph(f"{year}年{month}月 勤務表", title_style))
        elements.append(Spacer(1, 20))

        dates = sorted(list(set(a["date"] for a in assignments)))
        if not dates:
            last_day = calendar.monthrange(year, month)[1]
            dates = [f"{year}-{month:02d}-{d:02d}" for d in range(1, last_day + 1)]

        weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
        header_date_cells = [
            f"{d.split('-')[-1]}\n({weekdays_ja[datetime.datetime.strptime(d, '%Y-%m-%d').weekday()]})"
            for d in dates
        ]
        # 2列追加（時間、項目）
        header_row = ["", "氏名"] + header_date_cells + ["勤務日", "休日", "その他休日", "夜勤日数"]
        data = [header_row]

        assignment_map = {(a["employee_id"], a["date"]): a["shift_type"] for a in assignments}
        for emp in employees:
            work_days, paid_holidays, holidays, night_shifts = 0, 0, 0, 0
            row_shifts = []
            for d in dates:
                shift_name = assignment_map.get((emp["id"], d), "")
                row_shifts.append(shift_name)
                if shift_name and shift_name not in ["有", "休", "明"]:
                    work_days += 1
                if shift_name == "有":
                    paid_holidays += 1
                if shift_name in ["休", "明"]:
                    holidays += 1
                if "夜" in shift_name:
                    night_shifts += 1
            row = ["", emp["name"]] + row_shifts + [str(work_days), str(holidays), str(paid_holidays), str(night_shifts)]
            data.append(row)

        # --- 集計定義 ---
        constraint_hours = [7, 8, 9, 12, 13, 14, 16, 18, 19]
        summary_labels = {h: f"{h:02d}:00時点" for h in constraint_hours}
        summary_labels["late_night"] = "準夜勤(20-24時)"
        summary_labels["deep_night"] = "深夜勤(0-7時)"
        actual_counts = {label: {d: 0 for d in dates} for label in summary_labels.values()}

        # --- シフトがカバーする時間の逆引きマップを作成 ---
        shift_to_hours_map = {}
        if hourly_groups:
            for hour, shifts_with_offset in hourly_groups.items():
                for s_name, offset in shifts_with_offset:
                    if s_name not in shift_to_hours_map: shift_to_hours_map[s_name] = {}
                    shift_to_hours_map[s_name][hour] = offset

        # --- 実績人数の計算 ---
        date_to_idx = {d: i for i, d in enumerate(dates)}
        for assignment in assignments:
            shift_name, d_str = assignment["shift_type"], assignment["date"]
            if shift_name in ["休", "明", "有"]:
                continue

            covered_hours_info = shift_to_hours_map.get(shift_name)
            if not covered_hours_info:
                continue

            # 各時間帯のカウンタを一度だけインクリメントするためのセット
            target_dates_for_latenight = set()
            target_dates_for_deepnight = set()

            for hour, offset in covered_hours_info.items():
                target_date_str = None
                if offset == 0:
                    target_date_str = d_str
                elif offset == 1:
                    current_date_idx = date_to_idx.get(d_str)
                    if current_date_idx is not None and current_date_idx + 1 < len(dates):
                        target_date_str = dates[current_date_idx + 1]

                if not target_date_str:
                    continue

                # 日中時間帯の集計
                if hour in constraint_hours:
                    actual_counts[summary_labels[hour]][target_date_str] += 1
                
                # 準夜勤(20-24時)の対象日をセットに追加
                if 20 <= hour <= 23:
                    target_dates_for_latenight.add(target_date_str)

                # 深夜勤(0-7時)の対象日をセットに追加
                if 0 <= hour <= 6:
                    target_dates_for_deepnight.add(target_date_str)

            # セットに追加された日付に対して実績を+1する
            for target_date in target_dates_for_latenight:
                actual_counts[summary_labels["late_night"]][target_date] += 1
            for target_date in target_dates_for_deepnight:
                actual_counts[summary_labels["deep_night"]][target_date] += 1

        # --- 集計行の作成ロジック ---
        style_commands_for_summary = []
        base_row_idx = len(data)

        summary_header = ["時間", "項目"] + [f"{d.split('-')[-1]}" for d in dates] + ["", "", "", "", ""]
        data.append(summary_header)
        summary_header_row_idx = len(data) - 1
        style_commands_for_summary.append(('BACKGROUND', (0, summary_header_row_idx), (-1, summary_header_row_idx), colors.lightgrey))

        sorted_summary_keys = sorted(constraint_hours) + ["late_night", "deep_night"]
        
        for key in sorted_summary_keys:
            is_time_key = isinstance(key, int)
            
            if is_time_key:
                hour_str_key = f"{key:02d}00"
                time_label = f"{key:02d}:00"
                actual_row_values = [actual_counts[summary_labels[key]][d] for d in dates]
            elif key == "late_night":
                hour_str_key = "2000_next_0700" # 制約名は共通
                time_label = "20-24時"
                actual_row_values = [actual_counts[summary_labels["late_night"]][d] for d in dates]
            else: # deep_night
                hour_str_key = "2000_next_0700" # 制約名は共通
                time_label = "0-7時"
                actual_row_values = [actual_counts[summary_labels["deep_night"]][d] for d in dates]

            req_weekday_key = f"min_staff_weekday_{hour_str_key}"
            req_sunday_key = f"min_staff_sunday_{hour_str_key}"
            
            base_req = {d: staffing_requirements.get(req_sunday_key, 0) if datetime.datetime.strptime(d, "%Y-%m-%d").weekday() == 6 else staffing_requirements.get(req_weekday_key, 0) for d in dates}
            is_special_hour = is_time_key and key in [8, 9]
            
            block_start_row = len(data)

            if is_special_hour:
                data.append([time_label, "基本必要人数"] + [base_req[d] for d in dates] + [""]*5)
                
                num_visitors_list = []
                final_req_list = []
                for d in dates:
                    special_day_list = special_days.get(d, [])
                    num_visitors = 0
                    for special_day in special_day_list:
                        if special_day and special_day.visit_time and int(special_day.visit_time.split(':')[0]) == key:
                            num_visitors += special_day.staff_increase
                    num_visitors_list.append(str(num_visitors) if num_visitors > 0 else "0")
                    final_req_list.append(base_req[d] + num_visitors)
                
                data.append(["", "通院者数"] + num_visitors_list + [""]*5)
                data.append(["", "最終必要人数"] + final_req_list + [""]*5)
                data.append(["", "予定人数"] + actual_row_values + [""]*5)
                diff_values = [actual - final for actual, final in zip(actual_row_values, final_req_list)]
            else:
                req_list = [base_req[d] for d in dates]
                data.append([time_label, "必要人数"] + req_list + [""]*5)
                data.append(["", "予定人数"] + actual_row_values + [""]*5)
                diff_values = [actual - req for actual, req in zip(actual_row_values, req_list)]

            diff_row = ["", "過不足"]
            for i, diff in enumerate(diff_values):
                diff_row.append(f"+{diff}" if diff > 0 else str(diff))
                if diff < 0:
                    style_commands_for_summary.append(('BACKGROUND', (i + 2, len(data)), (i + 2, len(data)), colors.yellow))
            data.append(diff_row + [""]*5)

            block_end_row = len(data) - 1
            if block_start_row <= block_end_row:
                style_commands_for_summary.append(('SPAN', (0, block_start_row), (0, block_end_row)))
                style_commands_for_summary.append(('VALIGN', (0, block_start_row), (0, block_end_row), 'MIDDLE'))

        page_width = landscape(A4)[0] - 60
        # 列幅の計算を更新 (時間・項目列を追加)
        total_units = 1.0 + 1.5 + len(dates) + 5 
        unit_width = page_width / total_units
        col_widths = [unit_width * 1.0, unit_width * 1.5] + [unit_width] * len(dates) + [unit_width] * 5
        table = Table(data, colWidths=col_widths)

        num_employees = len(employees)
        style_commands = [
            ("FONTNAME", (0, 0), (-1, -1), self.font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), # main header
        ]
        
        # 集計行全体の背景色とスタイルコマンドを追加
        summary_start_row = 1 + num_employees
        style_commands.append(("BACKGROUND", (0, summary_start_row), (-1, -1), colors.whitesmoke))
        style_commands.extend(style_commands_for_summary)

        style = TableStyle(style_commands)
        
        # 曜日ごとのヘッダー色設定 (列インデックスを+1調整)
        for i, d_str in enumerate(dates):
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            wd = dt.weekday()
            col_idx = i + 2 # 2列追加したため
            if wd == 6: style.add("TEXTCOLOR", (col_idx, 0), (col_idx, 0), colors.red)
            elif wd == 5: style.add("TEXTCOLOR", (col_idx, 0), (col_idx, 0), colors.blue)

        # 従業員行のシフト色付け (列インデックスを+1調整)
        for row_idx in range(1, num_employees + 1):
            user_id = employees[row_idx - 1]["id"]
            for col_idx, cell_value in enumerate(data[row_idx][2 : len(dates) + 2], start=2):
                date_str = dates[col_idx - 2]
                if cell_value in ["休", "明", "有"]:
                    style.add("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.pink)
                elif "夜" in cell_value:
                    style.add("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.lightyellow)
                if (user_id, date_str) in highlight_cells:
                    style.add("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.red)
        
        # 項目列を左寄せにする
        style.add('ALIGN', (1, summary_start_row), (1, -1), 'LEFT')

        table.setStyle(style)
        elements.append(table)
        doc.build(elements)
        return buffer.getvalue()
