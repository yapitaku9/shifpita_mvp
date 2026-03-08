import pulp
import calendar
import logging
from datetime import date, timedelta, time
from app import db
from app.models.user import User, EmploymentType
from app.models.master import ShiftType, ShiftConstraint
from app.models.day_off_request import DayOffRequest
from app.models.work_request import WorkRequest
from app.models.desired_work_days_request import DesiredWorkDaysRequest
from app.models.shift import ShiftAssignment
from app.models.shift_history import ShiftHistory
from app.models.special_day import SpecialDay


class ShiftGenerator:
    """シフト生成エンジンクラス。"""
    def __init__(self):
        # --- DBからマスターデータを読み込む ---
        self.shift_types_by_id = {s.shift_type_id: s for s in db.session.query(ShiftType).all()}
        self.shift_types_by_name = {s.name: s for s in self.shift_types_by_id.values()}
        self.constraints = {c.name: c.value for c in db.session.query(ShiftConstraint).all()}

        # --- シフト定義 ---
        self.SHIFT_KYU = "休"
        self.SHIFT_AKE = "明"  # '明'は '夜勤明け' の意
        self.SHIFT_PAID_HOLIDAY = "有"  # 有給休暇

        self.SHIFTS_NIGHT = [st.name for st in self.shift_types_by_id.values() if "夜" in st.name]
        self.SHIFTS_LATE = [st.name for st in self.shift_types_by_id.values() if "遅" in st.name]
        self.SHIFTS_EARLY = [st.name for st in self.shift_types_by_id.values() if "早" in st.name]
        self.SHIFTS_DAY = [st.name for st in self.shift_types_by_id.values() if "日" in st.name]

        # 総勤務日数計算用のシフト（休み、明け以外）
        self.SHIFTS_FOR_WORK_COUNT = [
            s.name for s in self.shift_types_by_id.values() if s.name not in [self.SHIFT_KYU, self.SHIFT_AKE]
        ]
        self.SHIFTS_FOR_WORK_COUNT = list(set(self.SHIFTS_FOR_WORK_COUNT + [self.SHIFT_PAID_HOLIDAY]))
        # 連勤計算用の勤務シフト（休み、明け、有給以外）
        self.SHIFTS_WORK = [s for s in self.SHIFTS_FOR_WORK_COUNT if s != self.SHIFT_PAID_HOLIDAY]

        # 正社員の勤務シフト
        self.SHIFTS_FULL_TIME_WORK = [
            s for s in self.SHIFTS_WORK if s not in ["1", "2", "3", "4", "5", "6", "7", "8"]
        ]
        # 遅番または夜勤
        self.SHIFTS_LATE_OR_NIGHT = self.SHIFTS_LATE + self.SHIFTS_NIGHT

        # --- 時間帯別人員配置のためのグループ ---
        self.hourly_groups = {h: [] for h in range(24)}
        for st in self.shift_types_by_id.values():
            if st.name in [self.SHIFT_KYU, self.SHIFT_AKE]:
                continue
            if not st.start_time or not st.end_time:
                continue

            start_h = st.start_time.hour
            end_h = st.end_time.hour

            # 「夜2」シフトを「完全翌日勤務」として特別扱いする
            if "夜2" in st.name:
                for h in range(start_h, end_h):
                    # 常にオフセット1（翌日扱い）とする
                    self.hourly_groups[h].append((st.name, 1))
            elif start_h < end_h:  # 日中シフト
                for h in range(start_h, end_h):
                    self.hourly_groups[h].append((st.name, 0))
            else:  # 夜勤など日をまたぐシフト
                for h in range(start_h, 24):
                    self.hourly_groups[h].append((st.name, 0))
                for h in range(0, end_h):
                    self.hourly_groups[h].append((st.name, 1))

    def run(self, year: int, month: int) -> tuple[bool, list | str | None]:
        # --- 0. デバッグ用ロギング設定 ---
        logging.basicConfig(
            level=logging.DEBUG,
            filename="generator.log",
            filemode="w",
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        logging.info("Shift generation started.")

        # --- 1. データ準備 ---
        all_users = db.session.query(User).filter_by(is_admin=False).all()
        start_date = date(year, month, 1)
        end_date = date(year, month, calendar.monthrange(year, month)[1])
        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        date_strs = [d.isoformat() for d in dates]
        logging.info(f"Generating for {len(dates)} days.")

        # 前月のシフト履歴を取得
        prev_month_last_day = start_date - timedelta(days=1)
        # 連勤計算のために最大連勤日数+αの履歴を取得
        history_start_date = prev_month_last_day - timedelta(days=10)
        
        shift_history_records = ShiftHistory.query.filter(
            ShiftHistory.date.between(history_start_date, prev_month_last_day)
        ).all()
        
        # 扱いやすいように辞書に変換 { (user_id, 'YYYY-MM-DD'): shift_name }
        shift_history_map = {
            (rec.user_id, rec.date.isoformat()): rec.shift_type.name 
            for rec in shift_history_records
        }
        logging.info(f"Loaded {len(shift_history_records)} records from previous month's history.")

        # 承認済みの希望休と有給休暇を取得
        day_off_reqs = {}
        paid_leave_reqs = {}
        approved_day_offs = DayOffRequest.query.filter(
            DayOffRequest.date.between(start_date, end_date), DayOffRequest.status == "approved"
        ).all()
        for req in approved_day_offs:
            if req.request_type == 'paid_leave':
                paid_leave_reqs.setdefault(req.user_id, []).append(req.date.isoformat())
            else: # 'day_off'
                day_off_reqs.setdefault(req.user_id, []).append(req.date.isoformat())

        # 承認済みの希望勤務を取得
        work_req_map = {}
        approved_work_reqs = WorkRequest.query.filter(
            WorkRequest.date.between(start_date, end_date), WorkRequest.status == "approved"
        ).all()
        for req in approved_work_reqs:
            shift_names = [st.name for st in req.shift_types]
            if shift_names:
                work_req_map[(req.user_id, req.date.isoformat())] = shift_names

        # 特別日を取得
        special_days_map = {
            sd.date.isoformat(): sd
            for sd in SpecialDay.query.filter(SpecialDay.date.between(start_date, end_date)).all()
        }

        employees_data = [
            {
                "id": u.id,
                "name": u.full_name,
                "employment_type": u.employment_type,
                "max_consecutive_work_days": u.max_consecutive_work_days,
                "min_work_days": u.min_work_days,
                "max_work_days": u.max_work_days,
                "min_night_shifts": u.min_night_shifts,
                "max_night_shifts": u.max_night_shifts,
                "preferred_shift_1_id": u.preferred_shift_1_id,
                "preferred_shift_2_id": u.preferred_shift_2_id,
                "ng_shifts": u.ng_shifts,
            }
            for u in all_users
        ]
        logging.info(f"Processing {len(employees_data)} employees.")
        
        # 全シフト名（DBに「休」「明」「有」が無くても必ず含める。LPに変数が出力されるために必須）
        all_shift_names = list(set(self.shift_types_by_name.keys()) | {self.SHIFT_KYU, self.SHIFT_AKE, self.SHIFT_PAID_HOLIDAY})
        
        # --- 2. 問題定義 ---
        prob = pulp.LpProblem("ShiftScheduling", pulp.LpMinimize)
        x = pulp.LpVariable.dicts(
            "x",
            ((e["id"], d, s) for e in employees_data for d in date_strs for s in all_shift_names),
            0,
            1,
            pulp.LpBinary,
        )
        objective_terms = []
        logging.info("PuLP problem initialized.")

        # --- 3. 制約の定義 (構造を全面的に再設計) ---
        # 3.1 人員配置の制約 (日付ごとのループ)
        hourly_req_keys = [
            "0700", "0800", "0900", "1200", "1300", "1400",
            "1600", "1800", "1900", "2000_next_0700",
        ]
        for d_idx, d_str in enumerate(date_strs):
            current_date = date.fromisoformat(d_str)
            day_type = "sunday" if current_date.weekday() == 6 else "weekday"
            special_day_info = special_days_map.get(d_str)

            for key in hourly_req_keys:
                staff_increase = 0
                if special_day_info and special_day_info.staff_increase > 0 and special_day_info.visit_time:
                    visit_hour = int(special_day_info.visit_time.split(':')[0])
                    current_hour_str = key.split('_')[0][:2]
                    if current_hour_str.isdigit() and int(current_hour_str) == visit_hour:
                        staff_increase = special_day_info.staff_increase
    
                if key == "2000_next_0700":
                    req_staff_count = self.constraints.get(f"min_staff_{day_type}_2000_next_0700", 2)
                    shifts_for_hour = self.SHIFTS_NIGHT
                    if shifts_for_hour:
                        actual_staff = pulp.lpSum(
                            x[emp["id"], d_str, s] for emp in employees_data for s in shifts_for_hour
                        )
                        prob += (actual_staff == req_staff_count, f"HardMinStaff_{day_type}_{key}_{d_str}")
                else:
                    hour = int(key) // 100
                    req_staff_count = self.constraints.get(f"min_staff_{day_type}_{key}", 0)
                    shifts_for_hour_with_offset = self.hourly_groups.get(hour, [])
                    
                    if shifts_for_hour_with_offset:
                        staff_terms = []
                        for s_name, offset in shifts_for_hour_with_offset:
                            if offset == 0:
                                staff_terms.append(pulp.lpSum(x[emp["id"], d_str, s_name] for emp in employees_data))
                            elif offset == 1:
                                target_date = current_date - timedelta(days=1)
                                target_d_str = target_date.isoformat()
                                if target_date.month == month: # 月内
                                    staff_terms.append(pulp.lpSum(x[emp["id"], target_d_str, s_name] for emp in employees_data))
                                else: # 月またぎ
                                    # 履歴から前日の勤務者を集計
                                    prev_day_workers = sum(1 for emp in employees_data if shift_history_map.get((emp["id"], target_d_str)) == s_name)
                                    staff_terms.append(prev_day_workers)

                        actual_staff = pulp.lpSum(staff_terms)
                        shortfall = pulp.LpVariable(f"Shortfall_{d_str}_{key}", 0, None, pulp.LpInteger)
                        prob += (actual_staff + shortfall >= req_staff_count + staff_increase, f"SoftMinStaff_{day_type}_{key}_{d_str}")
                        objective_terms.append(shortfall * 10000000)

        # 3.2 従業員ごとの制約 (従業員ごとのループ)
        for emp in employees_data:
            emp_id = emp["id"]
            is_full_timer = emp["employment_type"] in [EmploymentType.MANAGER, EmploymentType.SUPPORT, EmploymentType.FULL_TIME]
            logging.debug(f"Defining constraints for employee {emp_id} ({emp['name']}).")

            for d_str in date_strs:
                prob += (pulp.lpSum(x[emp_id, d_str, s] for s in all_shift_names) == 1, f"OneShiftPerDay_{emp_id}_{d_str}")

            SHIFTS_PART_TIME_SHORT_WORK = ["1", "2", "3", "4", "5", "6", "7", "8"]
            if emp["employment_type"] == EmploymentType.PART_TIME_SHORT:
                allowed_shifts = SHIFTS_PART_TIME_SHORT_WORK + [self.SHIFT_KYU, self.SHIFT_PAID_HOLIDAY, self.SHIFT_AKE]
                forbidden_shifts = [s for s in all_shift_names if s not in allowed_shifts]
                for d_str in date_strs:
                    prob += (pulp.lpSum(x[emp_id, d_str, s] for s in forbidden_shifts) == 0, f"ForbiddenShifts_PartTimeShort_{emp_id}_{d_str}")
            else:
                for d_str in date_strs:
                    prob += (pulp.lpSum(x[emp_id, d_str, s] for s in SHIFTS_PART_TIME_SHORT_WORK) == 0, f"ForbiddenShifts_FullTime_{emp_id}_{d_str}")

            for d_str in date_strs:
                if d_str in day_off_reqs.get(emp_id, []):
                    prob += (x[emp_id, d_str, self.SHIFT_KYU] == 1, f"DayOffRequest_{emp_id}_{d_str}")
                elif d_str in paid_leave_reqs.get(emp_id, []):
                    prob += (x[emp_id, d_str, self.SHIFT_PAID_HOLIDAY] == 1, f"PaidLeaveRequest_{emp_id}_{d_str}")
                else:
                    prob += (x[emp_id, d_str, self.SHIFT_PAID_HOLIDAY] == 0, f"NoPaidHolidayWithoutRequest_{emp_id}_{d_str}")

                if (emp_id, d_str) in work_req_map:
                    requested_shifts = work_req_map.get((emp_id, d_str), [])
                    if self.SHIFT_PAID_HOLIDAY in requested_shifts and d_str not in paid_leave_reqs.get(emp_id, []):
                        filtered_requested_shifts = [s for s in requested_shifts if s != self.SHIFT_PAID_HOLIDAY]
                        if filtered_requested_shifts:
                             prob += (pulp.lpSum(x[emp_id, d_str, s] for s in filtered_requested_shifts) == 1, f"WorkRequest_{emp_id}_{d_str}")
                    else:
                        prob += (pulp.lpSum(x[emp_id, d_str, s] for s in requested_shifts) == 1, f"WorkRequest_{emp_id}_{d_str}")
            
            if emp.get("ng_shifts"):
                try:
                    ng_shift_ids = [int(sid) for sid in emp["ng_shifts"].split(",") if sid]
                    ng_shift_names = [self.shift_types_by_id[sid].name for sid in ng_shift_ids if sid in self.shift_types_by_id]
                    ng_shift_names = [s for s in ng_shift_names if s != self.SHIFT_KYU]
                    if ng_shift_names:
                        for d_str in date_strs:
                            prob += (pulp.lpSum(x[emp_id, d_str, s] for s in ng_shift_names) == 0, f"NGShifts_{emp_id}_{d_str}")
                except (ValueError, KeyError) as e:
                    logging.warning(f"Could not parse ng_shifts for employee {emp_id}: {emp.get('ng_shifts')}. Error: {e}")

            min_days = emp.get("min_work_days")
            max_days = emp.get("max_work_days")
            if min_days is not None:
                prob += (pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_FOR_WORK_COUNT) >= min_days, f"MinWorkDays_{emp_id}")
            if max_days is not None:
                prob += (pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_FOR_WORK_COUNT) <= max_days, f"MaxWorkDays_{emp_id}")

            min_night = emp.get("min_night_shifts")
            max_night = emp.get("max_night_shifts")
            if min_night is not None:
                prob += (pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_NIGHT) >= min_night, f"MinNightShifts_{emp_id}")
            if max_night is not None:
                prob += (pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_NIGHT) <= max_night, f"MaxNightShifts_{emp_id}")

            # 連勤制約
            max_consecutive = int(emp.get("max_consecutive_work_days") or self.constraints.get("max_consecutive_work_days", 5))
            if max_consecutive <= 0: max_consecutive = 5
            
            # 前月末からの連勤日数を計算
            consecutive_work_from_prev_month = 0
            for i in range(max_consecutive):
                d = prev_month_last_day - timedelta(days=i)
                if shift_history_map.get((emp_id, d.isoformat())) in self.SHIFTS_WORK:
                    consecutive_work_from_prev_month += 1
                else:
                    break
            logging.debug(f"Emp {emp_id}: consecutive work days from previous month = {consecutive_work_from_prev_month}")

            # 月初から最大連勤日数までの期間の制約
            for i in range(max_consecutive):
                # 前月からの連勤日数と、今月のi日目までの勤務日数の合計がmax_consecutiveを超えないようにする
                prob += (pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i + 1) for s in self.SHIFTS_WORK) + consecutive_work_from_prev_month <= max_consecutive, f"MaxConsecutiveWork_StartOfMonth_{emp_id}_{i}")

            # 月内の連勤制約 (従来通り)
            for i in range(len(dates) - max_consecutive):
                prob += (pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i, i + max_consecutive + 1) for s in self.SHIFTS_WORK) <= max_consecutive, f"MaxConsecutiveWork_MidMonth_{emp_id}_{i}")

            # 他の連勤制約（夜勤、遅番＋夜勤）も同様に月またぎを考慮する必要があるが、一旦メインの連勤のみ対応

            # シフト構成ルール
            all_dates_with_prev = [(d.isoformat(), (d - timedelta(days=1)).isoformat()) for d in dates]

            for d_str, prev_d_str in all_dates_with_prev:
                prev_date = date.fromisoformat(prev_d_str)

                # 前日が当月の場合
                if prev_date.month == month:
                    for night_shift in self.SHIFTS_NIGHT:
                        prob += (x[emp_id, prev_d_str, night_shift] <= pulp.lpSum(x[emp_id, d_str, s] for s in [self.SHIFT_AKE, self.SHIFT_KYU] + self.SHIFTS_NIGHT), f"NightMustBeFollowedByAkeOrNight_{emp_id}_{prev_d_str}_{night_shift}")
                    prob += (x[emp_id, d_str, self.SHIFT_AKE] <= pulp.lpSum(x[emp_id, prev_d_str, s] for s in self.SHIFTS_NIGHT), f"AkeOnlyAfterNight_{emp_id}_{d_str}")
                    
                    # 翌日への制約
                    next_d_str = (date.fromisoformat(d_str) + timedelta(days=1)).isoformat()
                    if next_d_str in date_strs:
                        if self.constraints.get("require_day_off_after_ake", 1) == 1:
                            prob += (x[emp_id, d_str, self.SHIFT_AKE] <= x[emp_id, next_d_str, self.SHIFT_KYU], f"RestAfterAke_{emp_id}_{d_str}")
                        if is_full_timer:
                            if self.constraints.get("disallow_specific_shifts_after_night", 1) == 1 and self.SHIFTS_NIGHT:
                                forbidden = self.SHIFTS_LATE + self.SHIFTS_DAY + self.SHIFTS_EARLY
                                for night_shift in self.SHIFTS_NIGHT:
                                    for f_shift in forbidden:
                                        prob += (x[emp_id, d_str, night_shift] + x[emp_id, next_d_str, f_shift] <= 1, f"No_{f_shift}_After_{night_shift}_{emp_id}_{d_str}")
                            if self.constraints.get("disallow_specific_shifts_after_late", 1) == 1 and self.SHIFTS_LATE:
                                forbidden = self.SHIFTS_DAY + self.SHIFTS_EARLY
                                for late_shift in self.SHIFTS_LATE:
                                    for f_shift in forbidden:
                                        prob += (x[emp_id, d_str, late_shift] + x[emp_id, next_d_str, f_shift] <= 1, f"No_{f_shift}_After_{late_shift}_{emp_id}_{d_str}")
                            if self.constraints.get("disallow_specific_shifts_after_day", 1) == 1 and self.SHIFTS_DAY:
                                forbidden = self.SHIFTS_EARLY
                                for day_shift in self.SHIFTS_DAY:
                                    for f_shift in forbidden:
                                        prob += (x[emp_id, d_str, day_shift] + x[emp_id, next_d_str, f_shift] <= 1, f"No_{f_shift}_After_{day_shift}_{emp_id}_{d_str}")
                
                # 前日が前月の場合 (月初日の処理)
                else:
                    prev_shift = shift_history_map.get((emp_id, prev_d_str))
                    logging.debug(f"Emp {emp_id} on {d_str}: previous day shift from history is {prev_shift}")
                    
                    # --- 履歴がある場合の処理 ---
                    if prev_shift:
                        if prev_shift in self.SHIFTS_NIGHT:
                            # 夜勤明けは「明」または「夜勤」のみ (休みは不可)
                            prob += (pulp.lpSum(x[emp_id, d_str, s] for s in [self.SHIFT_AKE] + self.SHIFTS_NIGHT) == 1, f"History_NightFollowedBy_{emp_id}_{d_str}")
                        
                        # 「明」は夜勤の翌日のみ
                        if prev_shift not in self.SHIFTS_NIGHT:
                            prob += (x[emp_id, d_str, self.SHIFT_AKE] == 0, f"History_NoAkeWithoutNight_{emp_id}_{d_str}")
                        
                        # 履歴に基づいた当日の禁止シフト
                        if is_full_timer:
                            if prev_shift in self.SHIFTS_NIGHT and self.constraints.get("disallow_specific_shifts_after_night", 1) == 1:
                                forbidden = self.SHIFTS_LATE + self.SHIFTS_DAY + self.SHIFTS_EARLY
                                for f_shift in forbidden:
                                    prob += (x[emp_id, d_str, f_shift] == 0, f"History_No_{f_shift}_After_Night_{emp_id}_{d_str}")
                            if prev_shift in self.SHIFTS_LATE and self.constraints.get("disallow_specific_shifts_after_late", 1) == 1:
                                forbidden = self.SHIFTS_DAY + self.SHIFTS_EARLY
                                for f_shift in forbidden:
                                    prob += (x[emp_id, d_str, f_shift] == 0, f"History_No_{f_shift}_After_Late_{emp_id}_{d_str}")
                            if prev_shift in self.SHIFTS_DAY and self.constraints.get("disallow_specific_shifts_after_day", 1) == 1:
                                forbidden = self.SHIFTS_EARLY
                                for f_shift in forbidden:
                                    prob += (x[emp_id, d_str, f_shift] == 0, f"History_No_{f_shift}_After_Day_{emp_id}_{d_str}")
                    
                    # --- 履歴がない場合のフォールバック処理 ---
                    else:
                        prob += (x[emp_id, d_str, self.SHIFT_AKE] == 0, f"NoAkeOnFirstDay_Fallback_{emp_id}")

            # 月初日の「明」禁止制約は、より詳細な履歴に基づく制約に置き換えるため削除済

        # --- 4. ソフト制約の定義 ---
        logging.info("Defining soft constraints.")
        # 4.1 人員配置の超過ペナルティ
        p1 = self.constraints.get("weight_exceed_staffing_1", 10)
        p2 = self.constraints.get("weight_exceed_staffing_2", 30)
        p3_plus = self.constraints.get("weight_exceed_staffing_3_plus", 100)
        for d_idx, d_str in enumerate(date_strs):
            current_date = date.fromisoformat(d_str)
            day_type = "sunday" if current_date.weekday() == 6 else "weekday"
            special_day_info = special_days_map.get(d_str)
            for key in hourly_req_keys:
                # 時間帯ごとに staff_increase を決定する
                staff_increase = 0
                if special_day_info and special_day_info.staff_increase > 0 and special_day_info.visit_time:
                    visit_hour = int(special_day_info.visit_time.split(':')[0])
                    current_hour_str = key.split('_')[0][:2]
                    if current_hour_str.isdigit() and int(current_hour_str) == visit_hour:
                        staff_increase = special_day_info.staff_increase

                if key == "2000_next_0700":
                    continue  # 夜勤帯はハード制約で超過がないためスキップ

                hour = int(key) // 100
                req_staff_count = self.constraints.get(f"min_staff_{day_type}_{key}", 0)
                shifts_for_hour_with_offset = self.hourly_groups.get(hour, [])

                if shifts_for_hour_with_offset:
                    staff_terms = []
                    for s_name, offset in shifts_for_hour_with_offset:
                        if offset == 0:
                            staff_terms.append(pulp.lpSum(x[emp["id"], d_str, s_name] for emp in employees_data))
                        elif offset == 1:
                            target_date = current_date - timedelta(days=1)
                            target_d_str = target_date.isoformat()
                            if target_date.month == month: # 月内
                                staff_terms.append(pulp.lpSum(x[emp["id"], target_d_str, s_name] for emp in employees_data))
                            else: # 月またぎ
                                # 履歴から前日の勤務者を集計
                                prev_day_workers = sum(1 for emp in employees_data if shift_history_map.get((emp["id"], target_d_str)) == s_name)
                                staff_terms.append(prev_day_workers)
                    
                    actual_staff = pulp.lpSum(staff_terms) if staff_terms else 0
                    
                    over_staff = pulp.LpVariable(f"OverStaff_{d_str}_{key}", 0, None, pulp.LpInteger)
                    # over_staff >= actual - required となるように制約を設定
                    prob += over_staff >= actual_staff - (req_staff_count + staff_increase)

                    is_1, is_2, is_3 = pulp.LpVariable.dicts(
                        f"OverStaffLevel_{d_str}_{key}", [1, 2, 3], 0, 1, pulp.LpBinary
                    )
                    max_staff = len(employees_data)

                    # is_k = 1 <=> over_staff >= k となるように制約を修正
                    # k=1
                    prob += over_staff >= is_1
                    prob += over_staff <= max_staff * is_1
                    # k=2
                    prob += over_staff >= 2 * is_2
                    prob += over_staff <= 1 + (max_staff - 1) * is_2
                    # k=3
                    prob += over_staff >= 3 * is_3
                    prob += over_staff <= 2 + (max_staff - 2) * is_3
                    
                    penalty = p1 * (is_1 - is_2) + p2 * (is_2 - is_3) + p3_plus * is_3
                    objective_terms.append(penalty)

        # 4.2 責任者とサポの同日勤務回避
        if self.constraints.get("avoid_charge_and_support_same_day", 1) == 1:
            charge_ids = [e["id"] for e in employees_data if e["employment_type"] == EmploymentType.MANAGER]
            support_ids = [e["id"] for e in employees_data if e["employment_type"] == EmploymentType.SUPPORT]
            weight = self.constraints.get("weight_avoid_charge_support", 1)
            for d_str in date_strs:
                for c_id in charge_ids:
                    for s_id in support_ids:
                        w = pulp.LpVariable(f"cowork_{c_id}_{s_id}_{d_str}", 0, 1, pulp.LpBinary)
                        prob += (
                            w
                            >= pulp.lpSum(x[c_id, d_str, s] for s in self.SHIFTS_WORK)
                            + pulp.lpSum(x[s_id, d_str, s] for s in self.SHIFTS_WORK)
                            - 1
                        )
                        objective_terms.append(w * weight)

        # 4.3 正職員の早番/日勤確保
        if self.constraints.get("ensure_main_staff_in_day_shift", 1) == 1:
            full_timer_ids = [
                e["id"]
                for e in employees_data
                if e["employment_type"]
                in [EmploymentType.MANAGER, EmploymentType.SUPPORT, EmploymentType.FULL_TIME]
            ]
            early_day_shifts = self.SHIFTS_EARLY + self.SHIFTS_DAY
            weight = self.constraints.get("weight_ensure_main_staff", 50)
            if early_day_shifts and full_timer_ids:
                for d_str in date_strs:
                    z = pulp.LpVariable(f"no_main_staff_in_day_{d_str}", 0, 1, pulp.LpBinary)
                    prob += (
                        pulp.lpSum(x[emp_id, d_str, s] for emp_id in full_timer_ids for s in early_day_shifts)
                        + z
                        >= 1
                    )
                    prob += pulp.lpSum(
                        x[emp_id, d_str, s] for emp_id in full_timer_ids for s in early_day_shifts
                    ) <= len(full_timer_ids) * (1 - z)
                    objective_terms.append(z * weight)

        # 4.4 4連続夜勤の回避 (ハード制約で上限4日の場合)
        max_consecutive_night = int(self.constraints.get("max_consecutive_night_shifts", 4))
        if max_consecutive_night == 4 and self.SHIFTS_NIGHT:
            weight = self.constraints.get("weight_avoid_4_night_streak", 10)
            for emp in employees_data:
                for i in range(len(dates) - 3):
                    v = pulp.LpVariable(f"is_4_night_streak_{emp['id']}_{i}", 0, 1, pulp.LpBinary)
                    four_days_of_nights = pulp.lpSum(
                        x[emp["id"], date_strs[j], s] for j in range(i, i + 4) for s in self.SHIFTS_NIGHT
                    )
                    prob += four_days_of_nights <= 3 + v
                    objective_terms.append(v * weight)

        # 4.5 優先シフトが採用されなかった場合のペナルティ
        weight = self.constraints.get("penalty_missed_preferred_shift", 10)
        for emp in employees_data:
            emp_id = emp["id"]
            pref_1_id = emp.get("preferred_shift_1_id")
            pref_2_id = emp.get("preferred_shift_2_id")
            preferred_shift_names = [
                st.name for st_id, st in self.shift_types_by_id.items() if st_id in [pref_1_id, pref_2_id]
            ]

            if preferred_shift_names:
                for d_str in date_strs:
                    is_working = pulp.lpSum(x[emp_id, d_str, s] for s in self.SHIFTS_WORK)
                    is_assigned_preferred = pulp.lpSum(x[emp_id, d_str, s] for s in preferred_shift_names)
                    penalty_term = is_working - is_assigned_preferred
                    objective_terms.append(penalty_term * weight)

        # --- 5. 目的関数設定とソルバー実行 ---
        logging.info("Solving problem...")
        prob += pulp.lpSum(objective_terms), "Objective"
        prob.writeLP("ShiftProblem.lp")  # デバッグ用
        solver = pulp.PULP_CBC_CMD(msg=True, logPath="solver.log")
        status = prob.solve(solver)
        logging.info(f"Solver finished with status: {pulp.LpStatus[status]}")

        # --- 6. 結果の分析と返却 ---
        logging.info("Analyzing results for constraint violations.")

        violated_constraints = []
        # 最適解が見つかった場合でも、緩和した制約が破られていないかチェック
        if status == pulp.LpStatusOptimal:
            for v in prob.variables():
                if v.name.startswith("Shortfall_") and v.varValue > 0:
                    # 変数名 'Shortfall_YYYY-MM-DD_HHMM' から情報をパース
                    try:
                        _, date_part, hour_key = v.name.split("_", 2)

                        dt_obj = date.fromisoformat(date_part)
                        date_jp = f"{dt_obj.month}月{dt_obj.day}日"
                        hour_jp = (
                            f"{int(hour_key) // 100:02d}:00"
                            if hour_key != "2000_next_0700"
                            else "20:00-翌7:00"
                        )

                        violated_constraints.append(f"{date_jp} {hour_jp} (不足: {int(v.varValue)}人)")
                    except (ValueError, IndexError):
                        # パース失敗時は、変数名をそのままログに出力
                        logging.warning(f"Could not parse shortfall variable name: {v.name}")

        # 制約違反があった場合は、詳細なエラーメッセージを返す
        if violated_constraints:
            # 日付順にソートして表示
            violated_constraints.sort()
            error_message = (
                "人員配置条件を満たせませんでした。下記の日時で人員が不足しています：\n"
                + "\n".join(violated_constraints)
            )
            logging.warning(error_message.replace("\n", " | "))
            return False, error_message

        # 上記以外の理由で最適解が見つからなかった場合
        if status not in [pulp.LpStatusOptimal]:
            prob.writeLP("ShiftProblem.lp")
            error_message = (
                f"シフト生成に失敗しました。解が見つかりませんでした (Status: {pulp.LpStatus[status]})"
            )
            logging.warning(error_message)
            return False, error_message

        # --- 7. 結果のDB保存 & PDF用データ作成 ---
        logging.info("Processing results.")
        try:
            db.session.query(ShiftAssignment).filter(
                ShiftAssignment.date.between(start_date, dates[-1])
            ).delete()

            assignments_to_add = []
            assignments_for_pdf = []
            for emp in employees_data:
                for d_str in date_strs:
                    for s_name in all_shift_names:
                        if round(pulp.value(x[emp["id"], d_str, s_name])) == 1:
                            shift_type = self.shift_types_by_name.get(s_name)
                            if shift_type is not None:
                                assignments_to_add.append(
                                    ShiftAssignment(
                                        date=date.fromisoformat(d_str),
                                        user_id=emp["id"],
                                        shift_type_id=shift_type.shift_type_id,
                                    )
                                )
                            else:
                                logging.warning(
                                    f"Shift type '{s_name}' not in master; skipping DB save for emp {emp['id']} on {d_str}."
                                )
                            assignments_for_pdf.append(
                                {"date": d_str, "employee_id": emp["id"], "shift_type": s_name}
                            )
                            break

            db.session.bulk_save_objects(assignments_to_add)
            db.session.commit()
            logging.info("Shift generation successful.")
            return True, assignments_for_pdf
        except Exception as e:
            db.session.rollback()
            logging.error("Error saving results to DB.", exc_info=True)
            return False, f"シフト結果のDB保存中にエラーが発生しました: {e}"
