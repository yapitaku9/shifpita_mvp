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
        month_dates = [d for d in dates if f"{year}-{month:02d}" in d]

        weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
        header_date_cells = [
            f"{d.split('-')[-1]}\n({weekdays_ja[datetime.datetime.strptime(d, '%Y-%m-%d').weekday()]})"
            for d in dates
        ]
        header_row = ["", "氏名"] + header_date_cells + ["勤務日", "休日", "その他休日", "夜勤日数"]
        data = [header_row]

        assignment_map = {(a["employee_id"], a["date"]): a["shift_type"] for a in assignments}
        
        #
        # 従業員のシフトと月次サマリー行を作成
        #
        for emp in employees:
            work_days, paid_holidays, holidays, night_shifts = 0, 0, 0, 0
            row_shifts = []
            for d in dates:
                shift_name = assignment_map.get((emp["id"], d), "")
                row_shifts.append(shift_name)
                # 当月のデータのみを集計対象とする
                if d in month_dates:
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

        # --- 日次集計の準備 ---
        num_prev_days = len(dates) - len(month_dates)
        style_commands_for_summary = []
        
        # --- 集計定義 ---
        constraint_hours = [7, 8, 9, 12, 13, 14, 16, 18, 19]
        summary_labels = {h: f"{h:02d}:00時点" for h in constraint_hours}
        summary_labels["late_night_1"] = "20-23時"
        summary_labels["late_night_2"] = "23-24時"
        summary_labels["deep_night"] = "24時から翌7時"
        actual_counts = {label: {d: 0 for d in dates} for label in summary_labels.values()}

        # --- シフト -> 時間のマッピングを準備 ---
        shift_to_hours_map = {}
        if hourly_groups:
            for hour, shifts_with_offset in hourly_groups.items():
                for s_name, offset in shifts_with_offset:
                    if s_name not in shift_to_hours_map: shift_to_hours_map[s_name] = {}
                    shift_to_hours_map[s_name][hour] = offset
        
        # --- 実績人数の計算（全日付対象） ---
        staff_by_category_date = {label: {d: set() for d in dates} for label in summary_labels.values()}
        for assignment in assignments:
            shift_name = assignment["shift_type"]
            emp_id = assignment["employee_id"]
            if shift_name in ["休", "明", "有"]: continue

            covered_hours_info = shift_to_hours_map.get(shift_name)
            if not covered_hours_info: continue
            
            assignment_date = datetime.datetime.strptime(assignment["date"], '%Y-%m-%d').date()
            for hour, offset in covered_hours_info.items():
                target_date = assignment_date + datetime.timedelta(days=offset)
                target_date_str = target_date.strftime('%Y-%m-%d')
                
                if target_date_str not in dates: continue

                if hour in constraint_hours: staff_by_category_date[summary_labels[hour]][target_date_str].add(emp_id)
                if 20 <= hour <= 22: staff_by_category_date[summary_labels["late_night_1"]][target_date_str].add(emp_id)
                if hour == 23: staff_by_category_date[summary_labels["late_night_2"]][target_date_str].add(emp_id)
                if 0 <= hour <= 6: staff_by_category_date[summary_labels["deep_night"]][target_date_str].add(emp_id)
        
        for label, dates_data in staff_by_category_date.items():
            for d_str, emp_ids_set in dates_data.items():
                actual_counts[label][d_str] = len(emp_ids_set)

        # --- 集計行の作成ロジック ---
        summary_header = ["時間", "項目"] + [f"{d.split('-')[-1]}" for d in dates] + ["", "", "", ""]
        data.append(summary_header)
        summary_header_row_idx = len(data) - 1
        style_commands_for_summary.append(('BACKGROUND', (0, summary_header_row_idx), (-1, summary_header_row_idx), colors.lightgrey))

        sorted_summary_keys = sorted(constraint_hours) + ["late_night_1", "late_night_2", "deep_night"]
        
        for key in sorted_summary_keys:
            is_time_key = isinstance(key, int)
            
            if is_time_key:
                hour_str_key, time_label = f"{key:02d}00", f"{key:02d}:00"
                actual_row_values = [actual_counts[summary_labels[key]][d] for d in dates]
            elif key == "late_night_1":
                hour_str_key, time_label = "2000_2300", "20-23時"
                actual_row_values = [actual_counts[summary_labels["late_night_1"]][d] for d in dates]
            elif key == "late_night_2":
                hour_str_key, time_label = "2300_0000", "23-24時"
                actual_row_values = [actual_counts[summary_labels["late_night_2"]][d] for d in dates]
            else: # deep_night
                hour_str_key, time_label = "0000_next_0700", "24時から翌7時"
                actual_row_values = [actual_counts[summary_labels["deep_night"]][d] for d in dates]

            req_weekday_key, req_sunday_key = f"min_staff_weekday_{hour_str_key}", f"min_staff_sunday_{hour_str_key}"
            
            base_req = {}
            for d in dates:
                if d in month_dates:
                    req_day = datetime.datetime.strptime(d, "%Y-%m-%d")
                    # 深夜(0-7時)の場合、前日の曜日に基づいて必要人数を計算
                    if key == "deep_night":
                        req_day -= datetime.timedelta(days=1)
                    
                    is_sunday = req_day.weekday() == 6
                    key_to_use = req_sunday_key if is_sunday else req_weekday_key
                    base_req[d] = staffing_requirements.get(key_to_use, 0)
                else:
                    base_req[d] = ""
            
            is_special_hour = is_time_key and key in [8, 9]
            block_start_row = len(data)

            # --- 必要人数、実績、過不足の行を作成 ---
            # 前月分は空白にする
            empty_prev_days = [""] * num_prev_days
            
            if is_special_hour:
                req_values = [base_req[d] for d in month_dates]
                data.append([time_label, "基本必要人数"] + empty_prev_days + req_values + [""]*4)
                
                num_visitors_list, final_req_list = [], []
                for d in month_dates:
                    num_visitors = sum(sd.staff_increase for sd in special_days.get(d, []) if sd.visit_time and int(sd.visit_time.split(':')[0]) == key)
                    num_visitors_list.append(str(num_visitors))
                    final_req_list.append(base_req[d] + num_visitors)
                
                data.append(["", "通院者数"] + empty_prev_days + num_visitors_list + [""]*4)
                data.append(["", "最終必要人数"] + empty_prev_days + final_req_list + [""]*4)
                
                # 予定人数は全日表示
                data.append(["", "予定人数"] + actual_row_values + [""]*4)
                
                # 過不足は当月のみ計算
                diff_values = [actual - final for actual, final in zip([actual_counts[summary_labels[key]][d] for d in month_dates], final_req_list)]
            else:
                req_list = [base_req[d] for d in month_dates]
                data.append([time_label, "必要人数"] + empty_prev_days + req_list + [""]*4)
                
                # 予定人数は全日表示
                data.append(["", "予定人数"] + actual_row_values + [""]*4)
                
                # 過不足は当月のみ計算
                diff_values = [actual - req for actual, req in zip([actual_counts[summary_labels[key]][d] for d in month_dates], req_list)]

            diff_row = ["", "過不足"] + empty_prev_days
            for i, diff in enumerate(diff_values):
                diff_row.append(f"+{diff}" if diff > 0 else str(diff))
                if diff < 0:
                    # スタイル設定の列インデックスは num_prev_days を考慮
                    style_commands_for_summary.append(('BACKGROUND', (i + 2 + num_prev_days, len(data)), (i + 2 + num_prev_days, len(data)), colors.yellow))
            data.append(diff_row + [""]*4)

            block_end_row = len(data) - 1
            if block_start_row <= block_end_row:
                style_commands_for_summary.append(('SPAN', (0, block_start_row), (0, block_end_row)))
                style_commands_for_summary.append(('VALIGN', (0, block_start_row), (0, block_end_row), 'MIDDLE'))

        page_width = landscape(A4)[0] - 60
        total_units = 1.0 + 1.5 + len(dates) + 4 # 従業員サマリー列の数を修正
        unit_width = page_width / total_units
        col_widths = [unit_width * 1.0, unit_width * 1.5] + [unit_width] * len(dates) + [unit_width] * 4
        table = Table(data, colWidths=col_widths)

        num_employees = len(employees)
        style_commands = [
            ("FONTNAME", (0, 0), (-1, -1), self.font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ]
        
        # 前月と当月の間に縦線を追加
        if num_prev_days > 0:
            separator_col_idx = 1 + num_prev_days
            style_commands.append(('LINEBEFORE', (separator_col_idx, 0), (separator_col_idx, -1), 1, colors.black))

        summary_start_row = 1 + num_employees
        style_commands.append(("BACKGROUND", (0, summary_start_row), (-1, -1), colors.whitesmoke))
        style_commands.extend(style_commands_for_summary)

        style = TableStyle(style_commands)
        
        for i, d_str in enumerate(dates):
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            wd = dt.weekday()
            col_idx = i + 2
            if wd == 6: style.add("TEXTCOLOR", (col_idx, 0), (col_idx, 0), colors.red)
            elif wd == 5: style.add("TEXTCOLOR", (col_idx, 0), (col_idx, 0), colors.blue)

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
        
        style.add('ALIGN', (1, summary_start_row), (1, -1), 'LEFT')

        table.setStyle(style)
        elements.append(table)
        doc.build(elements)
        return buffer.getvalue()
