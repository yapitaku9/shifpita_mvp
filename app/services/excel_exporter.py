import calendar
import datetime
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

class ExcelExporter:
    def generate(self, year, month, employees, shifts, 
                 day_off_reqs=None, paid_leave_reqs=None, work_req_map=None,
                 hourly_groups=None, staffing_requirements=None, special_days=None):
        """
        シフトデータからExcelワークブックを生成する
        """
        # --- Guard against None ---
        if day_off_reqs is None: day_off_reqs = {}
        if paid_leave_reqs is None: paid_leave_reqs = {}
        if work_req_map is None: work_req_map = {}
        if hourly_groups is None: hourly_groups = {}
        if staffing_requirements is None: staffing_requirements = {}
        if special_days is None: special_days = {}

        wb = Workbook()
        ws = wb.active
        ws.title = f"{year}年{month}月"

        # --- Style Definitions ---
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        center_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        left_alignment = Alignment(horizontal='left', vertical='center')
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        red_font = Font(color="FF0000", bold=True)
        bold_font = Font(bold=True)
        saturday_fill = PatternFill(start_color="E0F0FF", end_color="E0F0FF", fill_type="solid")
        sunday_fill = PatternFill(start_color="FFECEC", end_color="FFECEC", fill_type="solid")
        deficit_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid") # Yellow for deficit
        summary_header_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid") # Light grey

        shift_colors = {
            "早": "C6EFCE", "日": "FFEB9C", "遅": "D9E1F2", "夜": "A5A5A5",
            "明": "FFC7CE", "休": "FFC7CE", "有": "FFC7CE" # Pink for 明, 休, 有
        }
        
        # --- Data Pre-processing ---
        num_days = calendar.monthrange(year, month)[1]
        dates = [datetime.date(year, month, d) for d in range(1, num_days + 1)]
        shifts_by_user_date = {(s.user_id, s.date): s.shift_type.name for s in shifts}

        # --- Main Header ---
        ws.cell(row=1, column=1, value="氏名").font = header_font
        ws.cell(row=1, column=1).fill = header_fill
        ws.cell(row=1, column=1).border = thin_border
        ws.column_dimensions['A'].width = 18

        for day in dates:
            col = day.day + 1
            cell = ws.cell(row=1, column=col, value=f"{day.day}\n({day.strftime('%a')})")
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_alignment
            cell.border = thin_border
            ws.column_dimensions[get_column_letter(col)].width = 5
            if day.weekday() == 5:
                cell.fill = PatternFill(start_color="6495ED", end_color="6495ED", fill_type="solid")
            elif day.weekday() == 6:
                cell.fill = PatternFill(start_color="DC143C", end_color="DC143C", fill_type="solid")
        
        # --- Employee Summary Headers ---
        summary_headers = ["勤務日", "休日", "その他休日", "夜勤"]
        summary_start_col = num_days + 2
        for i, header in enumerate(summary_headers):
            col = summary_start_col + i
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            ws.column_dimensions[get_column_letter(col)].width = 6

        # --- Employee Rows ---
        for row_num, emp in enumerate(employees, start=2):
            ws.cell(row=row_num, column=1, value=emp.full_name).border = thin_border
            
            work_days, paid_holidays, holidays, night_shifts = 0, 0, 0, 0

            for day in dates:
                col = day.day + 1
                shift_name = shifts_by_user_date.get((emp.id, day))
                if shift_name is None and day in paid_leave_reqs.get(emp.id, []):
                    shift_name = "有"

                # Employee Summary Calculation
                if shift_name:
                    if shift_name not in ["有", "休", "明"]: work_days += 1
                    if shift_name == "有": paid_holidays += 1
                    if shift_name in ["休", "明"]: holidays += 1
                    if "夜" in shift_name: night_shifts += 1

                cell = ws.cell(row=row_num, column=col, value=shift_name)
                cell.alignment = center_alignment
                cell.border = thin_border

                # Highlight fulfilled requests
                if (day in day_off_reqs.get(emp.id, []) and shift_name == "休") or \
                   (day in paid_leave_reqs.get(emp.id, []) and shift_name == "有") or \
                   ((emp.id, day) in work_req_map and shift_name in work_req_map.get((emp.id, day), [])):
                    cell.font = red_font
                
                # Fill colors
                if shift_name in shift_colors:
                    cell.fill = PatternFill(start_color=shift_colors[shift_name], end_color=shift_colors[shift_name], fill_type="solid")
                elif shift_name is None:
                    if day.weekday() == 5: cell.fill = saturday_fill
                    elif day.weekday() == 6: cell.fill = sunday_fill
            
            # Write employee summary
            emp_summary_data = [work_days, holidays, paid_holidays, night_shifts]
            for i, value in enumerate(emp_summary_data):
                ws.cell(row=row_num, column=summary_start_col + i, value=value).border = thin_border
                ws.cell(row=row_num, column=summary_start_col + i).alignment = center_alignment

        # --- Daily Summary Rows (PDF Style) ---
        summary_start_row = len(employees) + 3
        
        # --- Hourly staffing calculation ---
        constraint_hours = [7, 8, 9, 12, 13, 14, 16, 18, 19]
        summary_labels = {h: f"{h:02d}:00時点" for h in constraint_hours}
        summary_labels["night"] = "夜勤帯(20-7時)"
        
        actual_counts = {label: {d: 0 for d in dates} for label in summary_labels.values()}
        
        full_shift_data = []
        for u in employees:
            for d in dates:
                s = shifts_by_user_date.get((u.id, d))
                if s is None and d in paid_leave_reqs.get(u.id, []): s = "有"
                if s: full_shift_data.append({'user_id': u.id, 'date': d, 'shift_name': s})

        shift_to_hours_map = defaultdict(dict)
        for hour, shifts_with_offset in hourly_groups.items():
            for s_name, offset in shifts_with_offset:
                shift_to_hours_map[s_name][hour] = offset

        for assignment in full_shift_data:
            shift, d = assignment["shift_name"], assignment["date"]
            if shift in ["休", "明", "有"]: continue
            if "夜" in shift: actual_counts[summary_labels["night"]][d] += 1
            if shift not in shift_to_hours_map: continue
            
            for hour, offset in shift_to_hours_map[shift].items():
                if hour not in constraint_hours: continue
                target_date = d + datetime.timedelta(days=offset)
                if target_date in dates:
                    actual_counts[summary_labels[hour]][target_date] += 1

        # --- Write summary rows ---
        ws.cell(row=summary_start_row, column=1, value="時間").border = thin_border
        ws.cell(row=summary_start_row, column=2, value="項目").border = thin_border
        for day in dates:
            ws.cell(row=summary_start_row, column=day.day + 1, value=day.day).border = thin_border
        
        for c in range(1, num_days + 2):
            ws.cell(row=summary_start_row, column=c).fill = summary_header_fill
            ws.cell(row=summary_start_row, column=c).font = bold_font

        current_row = summary_start_row + 1
        sorted_hours = sorted(constraint_hours) + ["night"]
        for hour in sorted_hours:
            is_night_row = (hour == "night")
            hour_str_key = "2000_next_0700" if is_night_row else f"{hour:02d}00"
            req_weekday_key = f"min_staff_{'weekday'}_{hour_str_key}"
            req_sunday_key = f"min_staff_{'sunday'}_{hour_str_key}"
            
            base_req = {d: staffing_requirements.get(req_sunday_key, 0) if d.weekday() == 6 else staffing_requirements.get(req_weekday_key, 0) for d in dates}
            
            time_label = f"{hour:02d}:00" if isinstance(hour, int) else "夜勤"
            is_special_hour = hour in [8, 9]

            block_start_row = current_row
            
            actual_row_values = [actual_counts[summary_labels['night' if is_night_row else hour]][d] for d in dates]

            if is_special_hour:
                ws.cell(row=current_row, column=2, value="基本必要人数").border = thin_border
                for d in dates: ws.cell(row=current_row, column=d.day + 1, value=base_req[d]).border = thin_border
                current_row += 1

                final_req_list = []
                ws.cell(row=current_row, column=2, value="通院者数").border = thin_border
                for d in dates:
                    special_day = special_days.get(d)
                    num_visitors = 0
                    if special_day and special_day.visit_time and int(special_day.visit_time.split(':')[0]) == hour:
                        num_visitors = special_day.staff_increase
                    ws.cell(row=current_row, column=d.day + 1, value=num_visitors).border = thin_border
                    final_req_list.append(base_req[d] + num_visitors)
                current_row += 1

                ws.cell(row=current_row, column=2, value="最終必要人数").border = thin_border
                for i, d in enumerate(dates): ws.cell(row=current_row, column=d.day + 1, value=final_req_list[i]).border = thin_border
                current_row += 1

                ws.cell(row=current_row, column=2, value="予定人数").border = thin_border
                for i, d in enumerate(dates): ws.cell(row=current_row, column=d.day + 1, value=actual_row_values[i]).border = thin_border
                current_row += 1

                ws.cell(row=current_row, column=2, value="過不足").border = thin_border
                for i, d in enumerate(dates):
                    diff = actual_row_values[i] - final_req_list[i]
                    cell = ws.cell(row=current_row, column=d.day + 1, value=f"+{diff}" if diff > 0 else str(diff))
                    cell.border = thin_border
                    if diff < 0: cell.fill = deficit_fill
                current_row += 1

            else: # Other hours
                ws.cell(row=current_row, column=2, value="必要人数").border = thin_border
                req_list = [base_req[d] for d in dates]
                for i, d in enumerate(dates): ws.cell(row=current_row, column=d.day + 1, value=req_list[i]).border = thin_border
                current_row += 1
                
                ws.cell(row=current_row, column=2, value="予定人数").border = thin_border
                for i, d in enumerate(dates): ws.cell(row=current_row, column=d.day + 1, value=actual_row_values[i]).border = thin_border
                current_row += 1

                ws.cell(row=current_row, column=2, value="過不足").border = thin_border
                for i, d in enumerate(dates):
                    diff = actual_row_values[i] - req_list[i]
                    cell = ws.cell(row=current_row, column=d.day + 1, value=f"+{diff}" if diff > 0 else str(diff))
                    cell.border = thin_border
                    if diff < 0: cell.fill = deficit_fill
                current_row += 1

            # Merge time label cells
            ws.merge_cells(start_row=block_start_row, start_column=1, end_row=current_row - 1, end_column=1)
            cell = ws.cell(row=block_start_row, column=1)
            cell.value = time_label
            cell.alignment = center_alignment
            cell.border = thin_border
            ws.cell(row=block_start_row, column=2).border = thin_border # Fix merged cell border

        return wb
