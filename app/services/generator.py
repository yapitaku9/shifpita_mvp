import pulp
import calendar
import logging
from datetime import date, timedelta, time
from app import db
from app.models.user import User, EmploymentType
from app.models.master import ShiftType, ShiftConstraint, ConstraintType
from app.models.day_off_request import DayOffRequest
from app.models.work_request import WorkRequest
from app.models.desired_work_days_request import DesiredWorkDaysRequest
from app.models.shift import ShiftAssignment
from app.models.shift_history import ShiftHistory
from app.models.special_day import SpecialDay


class ShiftGenerator:
    """シフト生成エンジンクラス。"""

    def __init__(self):
        """
        コンストラクタ。DBアクセスを含まない基本的な定義を初期化する。
        DBからのデータロードは run メソッド内で行う。
        """
        # --- シフト定義 (DBアクセス不要なもの) ---
        self.SHIFT_KYU = "休"
        self.SHIFT_AKE = "明"
        self.SHIFT_PAID_HOLIDAY = "有"

        # --- 時間帯別人員配置のためのグループ定義 (runメソッドで動的に構築) ---
        self.hourly_groups = {h: [] for h in range(24)}

    def _load_data_from_db(self):
        """DBからマスターデータや設定を読み込み、インスタンス変数に格納する。"""
        # --- DBからマスターデータを読み込む ---
        self.shift_types_by_id = {s.shift_type_id: s for s in db.session.query(ShiftType).all()}
        self.shift_types_by_name = {s.name: s for s in self.shift_types_by_id.values()}
        
        # 制約をオブジェクトとして読み込み、辞書に格納
        all_constraints = db.session.query(ShiftConstraint).all()
        self.constraints = {}
        for c in all_constraints:
            self.constraints[c.name] = {
                'value': c.value,
                'type': c.constraint_type,
                'penalty': c.penalty
            }

        # --- シフト定義 (DBデータに依存するもの) ---
        self.SHIFTS_NIGHT = [st.name for st in self.shift_types_by_id.values() if "夜" in st.name]
        self.SHIFTS_LATE = [st.name for st in self.shift_types_by_id.values() if "遅" in st.name]
        self.SHIFTS_EARLY = [st.name for st in self.shift_types_by_id.values() if "早" in st.name]
        self.SHIFTS_DAY = [st.name for st in self.shift_types_by_id.values() if "日" in st.name]

        self.SHIFTS_FOR_WORK_COUNT = [
            s.name
            for s in self.shift_types_by_id.values()
            if s.name not in [self.SHIFT_KYU, self.SHIFT_AKE, self.SHIFT_PAID_HOLIDAY]
        ]
        self.SHIFTS_WORK = self.SHIFTS_FOR_WORK_COUNT
        self.SHIFTS_FULL_TIME_WORK = [
            s for s in self.SHIFTS_WORK if s not in ["1", "2", "3", "4", "5", "6", "7", "8"]
        ]
        self.SHIFTS_LATE_OR_NIGHT = self.SHIFTS_LATE + self.SHIFTS_NIGHT

        # --- 禁止連続シフトペア (例: 早2 -> 早1) ---
        self.forbidden_consecutive_pairs = []
        shift_name_bases = ["早", "日", "遅", "夜"]
        all_shift_names_in_db = self.shift_types_by_name.keys()
        for base in shift_name_bases:
            s2_name = f"{base}2"
            s1_name = f"{base}1"
            if s2_name in all_shift_names_in_db and s1_name in all_shift_names_in_db:
                self.forbidden_consecutive_pairs.append((s2_name, s1_name))

        # --- 時間帯別人員配置のためのグループ ---
        # hourly_groupsを再初期化
        self.hourly_groups = {h: [] for h in range(24)}
        for st in self.shift_types_by_id.values():
            if st.name in [self.SHIFT_KYU, self.SHIFT_AKE]:
                continue
            if not st.start_time or not st.end_time:
                continue

            start_h = st.start_time.hour
            end_h = st.end_time.hour

            if "夜2" in st.name:
                for h in range(start_h, end_h):
                    self.hourly_groups[h].append((st.name, 1))
            elif start_h < end_h:
                for h in range(start_h, end_h):
                    self.hourly_groups[h].append((st.name, 0))
            else:
                for h in range(start_h, 24):
                    self.hourly_groups[h].append((st.name, 0))
                for h in range(0, end_h):
                    self.hourly_groups[h].append((st.name, 1))

    def run(self, year: int, month: int) -> tuple[bool, list | str | None]:
        # --- 0. データベースからデータをロード ---
        self._load_data_from_db()

        logging.basicConfig(
            level=logging.DEBUG,
            filename="generator.log",
            filemode="w",
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        logging.info("Shift generation started.")

        # --- 1. データ準備 ---
        all_users = db.session.query(User).filter_by(is_admin=False, is_active=True).all()
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
            (rec.user_id, rec.date.isoformat()): rec.shift_type.name for rec in shift_history_records
        }
        logging.info(f"Loaded {len(shift_history_records)} records from previous month's history.")

        # 承認済みの希望休と有給休暇を取得
        day_off_reqs = {}
        paid_leave_reqs = {}
        preferred_paid_leave_reqs = {}
        approved_day_offs = DayOffRequest.query.filter(
            DayOffRequest.date.between(start_date, end_date), DayOffRequest.status == "approved"
        ).all()
        for req in approved_day_offs:
            if req.request_type == "paid_leave":
                paid_leave_reqs.setdefault(req.user_id, []).append(req.date.isoformat())
            elif req.request_type == "preferred_paid_leave":
                preferred_paid_leave_reqs.setdefault(req.user_id, []).append(req.date.isoformat())
            else:  # 'day_off'
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
        special_days_list = SpecialDay.query.filter(SpecialDay.date.between(start_date, end_date)).all()
        special_days_map = {}
        for sd in special_days_list:
            special_days_map.setdefault(sd.date.isoformat(), []).append(sd)

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
        SHIFTS_PART_TIME_SHORT_WORK = ["1", "2", "3", "4", "5", "6", "7", "8"]
        HOSPITAL_SHIFTS = ["通8", "通9"]
        all_shift_names = list(
            set(self.shift_types_by_name.keys())
            | {self.SHIFT_KYU, self.SHIFT_AKE, self.SHIFT_PAID_HOLIDAY}
            | set(SHIFTS_PART_TIME_SHORT_WORK)
            | set(HOSPITAL_SHIFTS)
        )

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
        staffing_constraint_dates = dates + [dates[-1] + timedelta(days=1)]

        hourly_req_keys = [
            "0700", "0800", "0900", "1200", "1300", "1400", "1600", "1800", "1900",
            "2000", "2100", "2200", "2300", "0000", "0100", "0200", "0300", "0400", "0500", "0600",
        ]
        for d_idx, current_date in enumerate(staffing_constraint_dates):
            d_str = current_date.isoformat()

            keys_to_process = hourly_req_keys
            if current_date > dates[-1]:
                keys_to_process = [k for k in hourly_req_keys if 0 <= int(k) // 100 <= 6]

            for key in keys_to_process:
                hour = int(key) // 100

                is_early_morning_hour = 0 <= hour <= 6
                if is_early_morning_hour:
                    if d_idx == 0: continue
                    req_date = current_date - timedelta(days=1)
                else:
                    req_date = current_date

                req_day_type = "sunday" if req_date.weekday() == 6 else "weekday"
                req_special_day_infos = special_days_map.get(req_date.isoformat(), [])

                staff_increase = 0
                for special_day_info in req_special_day_infos:
                    if (special_day_info and special_day_info.staff_increase > 0 and special_day_info.visit_time):
                        visit_hour = int(special_day_info.visit_time.split(":")[0])
                        if not is_early_morning_hour and visit_hour == hour:
                            staff_increase += special_day_info.staff_increase

                if 20 <= hour <= 22:
                    constraint_key_suffix, default_req = "2000_2300", 2
                elif hour == 23:
                    constraint_key_suffix, default_req = "2300_0000", 2
                elif 0 <= hour <= 6:
                    constraint_key_suffix, default_req = "0000_next_0700", 2
                else:
                    constraint_key_suffix, default_req = key, 0

                req_staff_count = self.constraints.get(f"min_staff_{req_day_type}_{constraint_key_suffix}", {}).get('value', default_req)

                shifts_for_hour_with_offset = self.hourly_groups.get(hour, [])
                actual_staff = 0
                if shifts_for_hour_with_offset:
                    staff_terms = []
                    for s_name, offset in shifts_for_hour_with_offset:
                        target_d_str_for_worker = (current_date - timedelta(days=offset)).isoformat()
                        if (current_date - timedelta(days=offset)).month == month:
                            staff_terms.append(pulp.lpSum(x[emp["id"], target_d_str_for_worker, s_name] for emp in employees_data))
                        else:
                            prev_day_workers = sum(1 for emp in employees_data if shift_history_map.get((emp["id"], target_d_str_for_worker)) == s_name)
                            staff_terms.append(prev_day_workers)
                    actual_staff = pulp.lpSum(staff_terms) if staff_terms else 0
                
                # --- 動的な人員配置制約の適用 ---
                hour_group_name = ""
                control_constraint_name = ""
                if 7 <= hour < 20:
                    hour_group_name = "day"
                    control_constraint_name = "no_staff_variance_07_20"
                elif 20 <= hour < 24:
                    hour_group_name = "night"
                    control_constraint_name = "no_staff_variance_20_24"
                else: # 0 <= hour < 7
                    hour_group_name = "night"
                    control_constraint_name = "no_staff_variance_24_07"

                control_constraint = self.constraints.get(control_constraint_name, {})
                constraint_type = control_constraint.get('type', ConstraintType.INACTIVE)

                if constraint_type == ConstraintType.INACTIVE:
                    continue

                total_required = req_staff_count + staff_increase
                
                if constraint_type == ConstraintType.HARD:
                    prob += actual_staff == total_required, f"HardStaffing_{hour_group_name}_{d_str}_{key}"
                
                elif constraint_type == ConstraintType.SOFT:
                    shortfall_penalty = self.constraints.get(f'penalty_shortage_{hour_group_name}', {}).get('penalty', 0)
                    if shortfall_penalty > 0:
                        shortfall = pulp.LpVariable(f"Shortfall_{d_str}_{key}", 0, None, pulp.LpInteger)
                        prob += actual_staff + shortfall >= total_required, f"SoftMinStaff_{d_str}_{key}"
                        objective_terms.append(shortfall * shortfall_penalty)

                    overage_p1 = self.constraints.get(f'penalty_overage_1_{hour_group_name}', {}).get('penalty', 0)
                    overage_p2 = self.constraints.get(f'penalty_overage_2_{hour_group_name}', {}).get('penalty', 0)
                    overage_p3_plus = self.constraints.get(f'penalty_overage_3_plus_{hour_group_name}', {}).get('penalty', 0)

                    if overage_p1 > 0 or overage_p2 > 0 or overage_p3_plus > 0:
                        over_staff = pulp.LpVariable(f"OverStaff_{d_str}_{key}", 0, None, pulp.LpInteger)
                        prob += over_staff >= actual_staff - total_required, f"DefineOverStaff_{d_str}_{key}"
                        
                        is_1, is_2, is_3 = pulp.LpVariable.dicts(f"OverStaffLevel_{d_str}_{key}", [1, 2, 3], 0, 1, pulp.LpBinary)
                        max_staff = len(employees_data)
                        
                        prob += over_staff >= is_1
                        prob += over_staff <= max_staff * is_1
                        prob += over_staff >= 2 * is_2
                        prob += over_staff <= 1 + (max_staff - 1) * is_2
                        prob += over_staff >= 3 * is_3
                        prob += over_staff <= 2 + (max_staff - 2) * is_3
                        
                        penalty = overage_p1 * (is_1 - is_2) + overage_p2 * (is_2 - is_3) + overage_p3_plus * is_3
                        objective_terms.append(penalty)


        # 3.2 従業員ごとの制約 (従業員ごとのループ)
        for emp in employees_data:
            emp_id = emp["id"]
            is_full_timer = emp["employment_type"] in [
                EmploymentType.MANAGER,
                EmploymentType.SUPPORT,
                EmploymentType.FULL_TIME,
            ]
            logging.debug(f"Defining constraints for employee {emp_id} ({emp['name']}).")

            for d_str in date_strs:
                prob += (
                    pulp.lpSum(x[emp_id, d_str, s] for s in all_shift_names) == 1,
                    f"OneShiftPerDay_{emp_id}_{d_str}",
                )

            if emp["employment_type"] == EmploymentType.PART_TIME_SHORT:
                allowed_shifts = SHIFTS_PART_TIME_SHORT_WORK + [
                    self.SHIFT_KYU,
                    self.SHIFT_PAID_HOLIDAY,
                    self.SHIFT_AKE,
                ]
                forbidden_shifts = [s for s in all_shift_names if s not in allowed_shifts]
                for d_str in date_strs:
                    prob += (
                        pulp.lpSum(x[emp_id, d_str, s] for s in forbidden_shifts) == 0,
                        f"ForbiddenShifts_PartTimeShort_{emp_id}_{d_str}",
                    )

            if emp["employment_type"] == EmploymentType.HOSPITAL_VISIT_SUPPORT:
                # 2. 通院日のシフトを制御し、それ以外は強制的に休みにする
                for d_str in date_strs:
                    day_special_infos = special_days_map.get(d_str, [])
                    is_requested_off = d_str in day_off_reqs.get(emp_id, []) or d_str in paid_leave_reqs.get(
                        emp_id, []
                    )

                    if is_requested_off:
                        continue  # 休み希望は別制約で処理される

                    is_hospital_day_8 = any(sdi.visit_time == "08:00" for sdi in day_special_infos)
                    is_hospital_day_9 = any(sdi.visit_time == "09:00" for sdi in day_special_infos)

                    allowed_work_shifts = []
                    if is_hospital_day_8:
                        allowed_work_shifts.append("通8")
                    if is_hospital_day_9:
                        allowed_work_shifts.append("通9")

                    # この従業員が基本入れる勤務シフトを定義する
                    possible_work_shifts = [s for s in self.SHIFTS_WORK if s in HOSPITAL_SHIFTS]

                    if allowed_work_shifts:
                        # 通院日なので、許可された通院シフト以外の「勤務」を禁止
                        forbidden_work_shifts = [
                            s for s in possible_work_shifts if s not in allowed_work_shifts
                        ]
                        if forbidden_work_shifts:
                            prob += (
                                pulp.lpSum(x[emp_id, d_str, s] for s in forbidden_work_shifts) == 0,
                                f"HospitalSupport_ForbiddenWork_{emp_id}_{d_str}",
                            )
                    else:
                        # 通院日ではないので、この従業員は強制的に休み
                        prob += (
                            pulp.lpSum(x[emp_id, d_str, s] for s in possible_work_shifts) == 0,
                            f"HospitalSupport_ForceKyu_{emp_id}_{d_str}",
                        )

                # この従業員は、HOSPITAL_SHIFTS 以外の全ての SHIFTS_WORK には入れない、という一般的な制約も追加
                other_work_shifts = [s for s in self.SHIFTS_WORK if s not in HOSPITAL_SHIFTS]
                if other_work_shifts:
                    for d_str in date_strs:
                        prob += (
                            pulp.lpSum(x[emp_id, d_str, s] for s in other_work_shifts) == 0,
                            f"HospitalSupport_GeneralForbidden_{emp_id}_{d_str}",
                        )

            if emp["employment_type"] in [
                EmploymentType.MANAGER,
                EmploymentType.SUPPORT,
                EmploymentType.FULL_TIME,
                EmploymentType.PART_TIME_8H,
            ]:
                forbidden_shifts = SHIFTS_PART_TIME_SHORT_WORK + HOSPITAL_SHIFTS
                for d_str in date_strs:
                    prob += (
                        pulp.lpSum(x[emp_id, d_str, s] for s in forbidden_shifts) == 0,
                        f"ForbiddenShifts_Others_{emp_id}_{d_str}",
                    )

            for d_str in date_strs:
                if d_str in day_off_reqs.get(emp_id, []):
                    prob += (x[emp_id, d_str, self.SHIFT_KYU] == 1, f"DayOffRequest_{emp_id}_{d_str}")
                elif d_str in paid_leave_reqs.get(emp_id, []):
                    prob += (
                        x[emp_id, d_str, self.SHIFT_PAID_HOLIDAY] == 1,
                        f"PaidLeaveRequest_{emp_id}_{d_str}",
                    )
                elif d_str in preferred_paid_leave_reqs.get(emp_id, []):
                    constraint = self.constraints.get('prefer_paid_leave_as_holiday', {})
                    constraint_type = constraint.get('type', ConstraintType.INACTIVE)
                    
                    if constraint_type == ConstraintType.HARD:
                        # ハード制約：必ず「休み」を割り当てる
                        prob += x[emp_id, d_str, self.SHIFT_KYU] == 1, f"PreferredPaidLeave_Hard_{emp_id}_{d_str}"
                    elif constraint_type == ConstraintType.SOFT:
                        # ソフト制約：「有給」になった場合にペナルティ
                        penalty = constraint.get('penalty', 0)
                        # 「休」か「有」のどちらかを割り当てる
                        prob += (
                            x[emp_id, d_str, self.SHIFT_KYU] + x[emp_id, d_str, self.SHIFT_PAID_HOLIDAY] == 1,
                            f"PreferredPaidLeave_Base_{emp_id}_{d_str}",
                        )
                        # 「有」が割り当てられたらペナルティ
                        if penalty > 0:
                            objective_terms.append(x[emp_id, d_str, self.SHIFT_PAID_HOLIDAY] * penalty)
                    # INACTIVEの場合は何もしない（通常の勤務可能日として扱われる）

                else:
                    prob += (
                        x[emp_id, d_str, self.SHIFT_PAID_HOLIDAY] == 0,
                        f"NoPaidHolidayWithoutRequest_{emp_id}_{d_str}",
                    )

                if (emp_id, d_str) in work_req_map:
                    requested_shifts = work_req_map.get((emp_id, d_str), [])
                    if self.SHIFT_PAID_HOLIDAY in requested_shifts and d_str not in paid_leave_reqs.get(
                        emp_id, []
                    ):
                        filtered_requested_shifts = [
                            s for s in requested_shifts if s != self.SHIFT_PAID_HOLIDAY
                        ]
                        if filtered_requested_shifts:
                            prob += (
                                pulp.lpSum(x[emp_id, d_str, s] for s in filtered_requested_shifts) == 1,
                                f"WorkRequest_{emp_id}_{d_str}",
                            )
                    else:
                        prob += (
                            pulp.lpSum(x[emp_id, d_str, s] for s in requested_shifts) == 1,
                            f"WorkRequest_{emp_id}_{d_str}",
                        )

            if emp.get("ng_shifts"):
                try:
                    ng_shift_ids = [int(sid) for sid in emp["ng_shifts"].split(",") if sid]
                    ng_shift_names = [
                        self.shift_types_by_id[sid].name
                        for sid in ng_shift_ids
                        if sid in self.shift_types_by_id
                    ]
                    ng_shift_names = [s for s in ng_shift_names if s != self.SHIFT_KYU]
                    if ng_shift_names:
                        for d_str in date_strs:
                            prob += (
                                pulp.lpSum(x[emp_id, d_str, s] for s in ng_shift_names) == 0,
                                f"NGShifts_{emp_id}_{d_str}",
                            )
                except (ValueError, KeyError) as e:
                    logging.warning(
                        f"Could not parse ng_shifts for employee {emp_id}: {emp.get('ng_shifts')}. Error: {e}"
                    )

            # --- 勤務日数・夜勤日数の制約 (動的) ---
            total_work_days = pulp.lpSum(
                x[emp_id, d, s]
                for d in date_strs
                for s in self.SHIFTS_FOR_WORK_COUNT + [self.SHIFT_PAID_HOLIDAY]
            )
            total_night_shifts = pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_NIGHT)

            # 勤務日数
            work_days_config = self.constraints.get('penalty_for_work_day_violation', {})
            work_days_type = work_days_config.get('type', ConstraintType.INACTIVE)
            if work_days_type != ConstraintType.INACTIVE:
                # 最小勤務日数
                min_days_value = emp.get("min_work_days")
                if min_days_value is not None:
                    if work_days_type == ConstraintType.HARD:
                        prob += total_work_days >= min_days_value, f"HardMinWorkDays_{emp_id}"
                    elif work_days_type == ConstraintType.SOFT:
                        shortage = pulp.LpVariable(f"work_days_shortage_{emp_id}", 0, None, pulp.LpInteger)
                        prob += total_work_days + shortage >= min_days_value, f"SoftMinWorkDays_{emp_id}"
                        penalty = work_days_config.get('penalty', 0)
                        if penalty > 0:
                            objective_terms.append(shortage * penalty)
                # 最大勤務日数
                max_days_value = emp.get("max_work_days")
                if max_days_value is not None:
                    if work_days_type == ConstraintType.HARD:
                        prob += total_work_days <= max_days_value, f"HardMaxWorkDays_{emp_id}"
                    elif work_days_type == ConstraintType.SOFT:
                        excess = pulp.LpVariable(f"work_days_excess_{emp_id}", 0, None, pulp.LpInteger)
                        prob += total_work_days - excess <= max_days_value, f"SoftMaxWorkDays_{emp_id}"
                        penalty = work_days_config.get('penalty', 0)
                        if penalty > 0:
                            objective_terms.append(excess * penalty)

            # 夜勤日数
            night_shifts_config = self.constraints.get('penalty_for_night_shift_violation', {})
            night_shifts_type = night_shifts_config.get('type', ConstraintType.INACTIVE)
            if night_shifts_type != ConstraintType.INACTIVE:
                # 最小夜勤日数
                min_night_value = emp.get("min_night_shifts")
                if min_night_value is not None:
                    if night_shifts_type == ConstraintType.HARD:
                        prob += total_night_shifts >= min_night_value, f"HardMinNightShifts_{emp_id}"
                    elif night_shifts_type == ConstraintType.SOFT:
                        shortage = pulp.LpVariable(f"night_shifts_shortage_{emp_id}", 0, None, pulp.LpInteger)
                        prob += total_night_shifts + shortage >= min_night_value, f"SoftMinNightShifts_{emp_id}"
                        penalty = night_shifts_config.get('penalty', 0)
                        if penalty > 0:
                            objective_terms.append(shortage * penalty)
                # 最大夜勤日数
                max_night_value = emp.get("max_night_shifts")
                if max_night_value is not None:
                    if night_shifts_type == ConstraintType.HARD:
                        prob += total_night_shifts <= max_night_value, f"HardMaxNightShifts_{emp_id}"
                    elif night_shifts_type == ConstraintType.SOFT:
                        excess = pulp.LpVariable(f"night_shifts_excess_{emp_id}", 0, None, pulp.LpInteger)
                        prob += total_night_shifts - excess <= max_night_value, f"SoftMaxNightShifts_{emp_id}"
                        penalty = night_shifts_config.get('penalty', 0)
                        if penalty > 0:
                            objective_terms.append(excess * penalty)

            # --- 連勤制約 (動的) ---

            # 1. 最大連勤日数 (max_consecutive_work)
            work_cons_config = self.constraints.get('max_consecutive_work', {})
            work_cons_type = work_cons_config.get('type', ConstraintType.INACTIVE)
            if work_cons_type != ConstraintType.INACTIVE:
                max_consecutive = emp.get('max_consecutive_work_days')
                if max_consecutive is None:
                    max_consecutive = work_cons_config.get('value')

                if max_consecutive is not None and max_consecutive > 0:
                    consecutive_work_from_prev_month = 0
                    for i in range(max_consecutive):
                        d = prev_month_last_day - timedelta(days=i)
                        if shift_history_map.get((emp_id, d.isoformat())) in self.SHIFTS_WORK:
                            consecutive_work_from_prev_month += 1
                        else:
                            break
                    
                    if consecutive_work_from_prev_month > 0:
                        for i in range(max_consecutive):
                            work_sum = pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i + 1) for s in self.SHIFTS_WORK)
                            condition = work_sum + consecutive_work_from_prev_month <= max_consecutive
                            if work_cons_type == ConstraintType.HARD:
                                prob += condition, f"HardMaxConsecutiveWork_Start_{emp_id}_{i}"
                            elif work_cons_type == ConstraintType.SOFT:
                                excess = pulp.LpVariable(f"ExcessWork_Start_{emp_id}_{i}", 0, None, pulp.LpInteger)
                                prob += work_sum + consecutive_work_from_prev_month - excess <= max_consecutive, f"SoftMaxConsecutiveWork_Start_{emp_id}_{i}"
                                objective_terms.append(excess * work_cons_config.get('penalty', 0))

                    for i in range(len(dates) - max_consecutive):
                        work_sum = pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i, i + max_consecutive + 1) for s in self.SHIFTS_WORK)
                        condition = work_sum <= max_consecutive
                        if work_cons_type == ConstraintType.HARD:
                            prob += condition, f"HardMaxConsecutiveWork_Mid_{emp_id}_{i}"
                        elif work_cons_type == ConstraintType.SOFT:
                            excess = pulp.LpVariable(f"ExcessWork_Mid_{emp_id}_{i}", 0, None, pulp.LpInteger)
                            prob += work_sum - excess <= max_consecutive, f"SoftMaxConsecutiveWork_Mid_{emp_id}_{i}"
                            objective_terms.append(excess * work_cons_config.get('penalty', 0))

            # 2. 遅番の最大連勤日数 (max_consecutive_late_shifts)
            late_cons_config = self.constraints.get('max_consecutive_late_shifts', {})
            late_cons_type = late_cons_config.get('type', ConstraintType.INACTIVE)
            if self.SHIFTS_LATE and late_cons_type != ConstraintType.INACTIVE:
                max_consecutive_late = late_cons_config.get('value')
                if max_consecutive_late is not None and max_consecutive_late > 0:
                    consecutive_late_from_prev_month = 0
                    for i in range(max_consecutive_late):
                        d = prev_month_last_day - timedelta(days=i)
                        if shift_history_map.get((emp_id, d.isoformat())) in self.SHIFTS_LATE:
                            consecutive_late_from_prev_month += 1
                        else:
                            break
                    
                    if consecutive_late_from_prev_month > 0:
                        for i in range(max_consecutive_late):
                            late_sum = pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i + 1) for s in self.SHIFTS_LATE)
                            condition = late_sum + consecutive_late_from_prev_month <= max_consecutive_late
                            if late_cons_type == ConstraintType.HARD:
                                prob += condition, f"HardMaxConsecutiveLate_Start_{emp_id}_{i}"
                            elif late_cons_type == ConstraintType.SOFT:
                                excess = pulp.LpVariable(f"ExcessLate_Start_{emp_id}_{i}", 0, None, pulp.LpInteger)
                                prob += late_sum + consecutive_late_from_prev_month - excess <= max_consecutive_late, f"SoftMaxConsecutiveLate_Start_{emp_id}_{i}"
                                objective_terms.append(excess * late_cons_config.get('penalty', 0))

                    for i in range(len(dates) - max_consecutive_late):
                        late_sum = pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i, i + max_consecutive_late + 1) for s in self.SHIFTS_LATE)
                        condition = late_sum <= max_consecutive_late
                        if late_cons_type == ConstraintType.HARD:
                            prob += condition, f"HardMaxConsecutiveLate_Mid_{emp_id}_{i}"
                        elif late_cons_type == ConstraintType.SOFT:
                            excess = pulp.LpVariable(f"ExcessLate_Mid_{emp_id}_{i}", 0, None, pulp.LpInteger)
                            prob += late_sum - excess <= max_consecutive_late, f"SoftMaxConsecutiveLate_Mid_{emp_id}_{i}"
                            objective_terms.append(excess * late_cons_config.get('penalty', 0))

            # 3. 夜勤の最大連勤日数 (max_consecutive_night_shifts)
            night_cons_config = self.constraints.get('max_consecutive_night_shifts', {})
            night_cons_type = night_cons_config.get('type', ConstraintType.INACTIVE)
            if self.SHIFTS_NIGHT and night_cons_type != ConstraintType.INACTIVE:
                max_consecutive_night = night_cons_config.get('value')
                if max_consecutive_night is not None and max_consecutive_night > 0:
                    consecutive_night_from_prev_month = 0
                    for i in range(max_consecutive_night):
                        d = prev_month_last_day - timedelta(days=i)
                        if shift_history_map.get((emp_id, d.isoformat())) in self.SHIFTS_NIGHT:
                            consecutive_night_from_prev_month += 1
                        else:
                            break
                    
                    if consecutive_night_from_prev_month > 0:
                        for i in range(max_consecutive_night):
                            night_sum = pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i + 1) for s in self.SHIFTS_NIGHT)
                            condition = night_sum + consecutive_night_from_prev_month <= max_consecutive_night
                            if night_cons_type == ConstraintType.HARD:
                                prob += condition, f"HardMaxConsecutiveNight_Start_{emp_id}_{i}"
                            elif night_cons_type == ConstraintType.SOFT:
                                excess = pulp.LpVariable(f"ExcessNight_Start_{emp_id}_{i}", 0, None, pulp.LpInteger)
                                prob += night_sum + consecutive_night_from_prev_month - excess <= max_consecutive_night, f"SoftMaxConsecutiveNight_Start_{emp_id}_{i}"
                                objective_terms.append(excess * night_cons_config.get('penalty', 0))

                    for i in range(len(dates) - max_consecutive_night):
                        night_sum = pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i, i + max_consecutive_night + 1) for s in self.SHIFTS_NIGHT)
                        condition = night_sum <= max_consecutive_night
                        if night_cons_type == ConstraintType.HARD:
                            prob += condition, f"HardMaxConsecutiveNight_Mid_{emp_id}_{i}"
                        elif night_cons_type == ConstraintType.SOFT:
                            excess = pulp.LpVariable(f"ExcessNight_Mid_{emp_id}_{i}", 0, None, pulp.LpInteger)
                            prob += night_sum - excess <= max_consecutive_night, f"SoftMaxConsecutiveNight_Mid_{emp_id}_{i}"
                            objective_terms.append(excess * night_cons_config.get('penalty', 0))

            # 4. 遅番+夜勤の最大連勤日数 (max_consecutive_late_night_shifts)
            late_night_cons_config = self.constraints.get('max_consecutive_late_night_shifts', {})
            late_night_cons_type = late_night_cons_config.get('type', ConstraintType.INACTIVE)
            late_and_night_shifts = self.SHIFTS_LATE_OR_NIGHT
            if late_and_night_shifts and late_night_cons_type != ConstraintType.INACTIVE:
                max_consecutive_late_night = late_night_cons_config.get('value')
                if max_consecutive_late_night is not None and max_consecutive_late_night > 0:
                    consecutive_late_night_from_prev_month = 0
                    for i in range(max_consecutive_late_night):
                        d = prev_month_last_day - timedelta(days=i)
                        if shift_history_map.get((emp_id, d.isoformat())) in late_and_night_shifts:
                            consecutive_late_night_from_prev_month += 1
                        else:
                            break
                    
                    if consecutive_late_night_from_prev_month > 0:
                        for i in range(max_consecutive_late_night):
                            late_night_sum = pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i + 1) for s in late_and_night_shifts)
                            condition = late_night_sum + consecutive_late_night_from_prev_month <= max_consecutive_late_night
                            if late_night_cons_type == ConstraintType.HARD:
                                prob += condition, f"HardMaxConsecutiveLateNight_Start_{emp_id}_{i}"
                            elif late_night_cons_type == ConstraintType.SOFT:
                                excess = pulp.LpVariable(f"ExcessLateNight_Start_{emp_id}_{i}", 0, None, pulp.LpInteger)
                                prob += late_night_sum + consecutive_late_night_from_prev_month - excess <= max_consecutive_late_night, f"SoftMaxConsecutiveLateNight_Start_{emp_id}_{i}"
                                objective_terms.append(excess * late_night_cons_config.get('penalty', 0))

                    for i in range(len(dates) - max_consecutive_late_night):
                        late_night_sum = pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i, i + max_consecutive_late_night + 1) for s in late_and_night_shifts)
                        condition = late_night_sum <= max_consecutive_late_night
                        if late_night_cons_type == ConstraintType.HARD:
                            prob += condition, f"HardMaxConsecutiveLateNight_Mid_{emp_id}_{i}"
                        elif late_night_cons_type == ConstraintType.SOFT:
                            excess = pulp.LpVariable(f"ExcessLateNight_Mid_{emp_id}_{i}", 0, None, pulp.LpInteger)
                            prob += late_night_sum - excess <= max_consecutive_late_night, f"SoftMaxConsecutiveLateNight_Mid_{emp_id}_{i}"
                            objective_terms.append(excess * late_night_cons_config.get('penalty', 0))


            # --- シフト構成ルール (動的) ---
            all_dates_with_next = [(d.isoformat(), (d + timedelta(days=1)).isoformat()) for d in dates[:-1]]
            ake_rest_config = self.constraints.get('holiday_after_ake', {})
            night_follow_config = self.constraints.get('forbidden_shift_after_night_shift', {})
            late_follow_config = self.constraints.get('forbidden_shift_after_late_shift', {})
            day_follow_config = self.constraints.get('forbidden_shift_after_day_shift', {})

            # 月初の処理 (前月最終日 -> 当月1日)
            first_day_str = date_strs[0]
            prev_to_first_day_str = (start_date - timedelta(days=1)).isoformat()
            prev_shift = shift_history_map.get((emp_id, prev_to_first_day_str))
            if prev_shift:
                # 夜勤明け (これは基本ルールとして維持)
                if prev_shift in self.SHIFTS_NIGHT:
                    prob += (pulp.lpSum(x[emp_id, first_day_str, s] for s in [self.SHIFT_AKE] + self.SHIFTS_NIGHT) == 1, f"History_NightFollowedBy_{emp_id}_{first_day_str}")
                else:
                    prob += (x[emp_id, first_day_str, self.SHIFT_AKE] == 0, f"History_NoAkeWithoutNight_{emp_id}_{first_day_str}")

                # 明けの翌日は休み
                if prev_shift == self.SHIFT_AKE and ake_rest_config.get('type') != ConstraintType.INACTIVE:
                    if ake_rest_config.get('type') == ConstraintType.HARD:
                        prob += x[emp_id, first_day_str, self.SHIFT_KYU] == 1, f"History_RestAfterAke_{emp_id}_{first_day_str}"
                    elif ake_rest_config.get('type') == ConstraintType.SOFT:
                        penalty = ake_rest_config.get('penalty', 0)
                        if penalty > 0:
                            violation = 1 - x[emp_id, first_day_str, self.SHIFT_KYU]
                            objective_terms.append(violation * penalty)
                
                # 履歴に基づいた禁止シフト
                def apply_history_follow_constraint(prev_s, forbidden_shifts, config, shift_name):
                    nonlocal prob, objective_terms
                    if prev_shift in prev_s and config.get('type') != ConstraintType.INACTIVE:
                        if config.get('type') == ConstraintType.HARD:
                            prob += pulp.lpSum(x[emp_id, first_day_str, s] for s in forbidden_shifts) == 0, f"History_No{shift_name}After_{emp_id}"
                        elif config.get('type') == ConstraintType.SOFT:
                            penalty = config.get('penalty', 0)
                            if penalty > 0:
                                violation = pulp.lpSum(x[emp_id, first_day_str, s] for s in forbidden_shifts)
                                objective_terms.append(violation * penalty)

                apply_history_follow_constraint(self.SHIFTS_NIGHT, self.SHIFTS_LATE + self.SHIFTS_DAY + self.SHIFTS_EARLY, night_follow_config, "Shift")
                apply_history_follow_constraint(self.SHIFTS_LATE, self.SHIFTS_DAY + self.SHIFTS_EARLY, late_follow_config, "Shift")
                apply_history_follow_constraint(self.SHIFTS_DAY, self.SHIFTS_EARLY, day_follow_config, "Shift")

                # 禁止連続ペア (例: 早2 -> 早1)
                for prev_s, next_s in self.forbidden_consecutive_pairs:
                    if prev_shift == prev_s:
                        prob += (x[emp_id, first_day_str, next_s] == 0, f"History_ForbiddenPair_{prev_s}_{next_s}_{emp_id}_{first_day_str}")
            else:
                prob += (x[emp_id, first_day_str, self.SHIFT_AKE] == 0, f"NoAkeOnFirstDay_Fallback_{emp_id}")

            # 月内 (1日->2日, ..., 最終日-1 -> 最終日)
            for d_str, next_d_str in all_dates_with_next:
                # 夜勤 -> 明け or 夜勤 (基本ルール)
                for night_shift in self.SHIFTS_NIGHT:
                    prob += (x[emp_id, d_str, night_shift] <= pulp.lpSum(x[emp_id, next_d_str, s] for s in [self.SHIFT_AKE] + self.SHIFTS_NIGHT), f"NightToAkeOrNight_{emp_id}_{d_str}_{night_shift}")
                # 明けは夜勤の翌日のみ (基本ルール)
                prob += (x[emp_id, next_d_str, self.SHIFT_AKE] <= pulp.lpSum(x[emp_id, d_str, s] for s in self.SHIFTS_NIGHT), f"AkeOnlyAfterNight_{emp_id}_{next_d_str}")

                # 明け -> 休み
                if ake_rest_config.get('type') != ConstraintType.INACTIVE:
                    if ake_rest_config.get('type') == ConstraintType.HARD:
                        prob += x[emp_id, d_str, self.SHIFT_AKE] <= x[emp_id, next_d_str, self.SHIFT_KYU], f"RestAfterAke_{emp_id}_{d_str}"
                    elif ake_rest_config.get('type') == ConstraintType.SOFT:
                        penalty = ake_rest_config.get('penalty', 0)
                        if penalty > 0:
                            violation = pulp.LpVariable(f"V_RestAfterAke_{emp_id}_{d_str}", 0, 1)
                            prob += x[emp_id, d_str, self.SHIFT_AKE] - x[emp_id, next_d_str, self.SHIFT_KYU] <= violation
                            objective_terms.append(violation * penalty)
                
                # 禁止シフトパターン
                def apply_internal_follow_constraint(shifts, forbidden_shifts, config, name):
                    nonlocal prob, objective_terms
                    if shifts and config.get('type') != ConstraintType.INACTIVE:
                        for prev_s in shifts:
                            for next_s in forbidden_shifts:
                                if config.get('type') == ConstraintType.HARD:
                                    prob += x[emp_id, d_str, prev_s] + x[emp_id, next_d_str, next_s] <= 1, f"No_{next_s}_After_{prev_s}_{emp_id}_{d_str}"
                                elif config.get('type') == ConstraintType.SOFT:
                                    penalty = config.get('penalty', 0)
                                    if penalty > 0:
                                        violation = pulp.LpVariable(f"V_{name}_{prev_s}_{next_s}_{emp_id}_{d_str}", 0, 1, pulp.LpBinary)
                                        prob += x[emp_id, d_str, prev_s] + x[emp_id, next_d_str, next_s] - 1 <= violation
                                        objective_terms.append(violation * penalty)
                
                apply_internal_follow_constraint(self.SHIFTS_NIGHT, self.SHIFTS_LATE + self.SHIFTS_DAY + self.SHIFTS_EARLY, night_follow_config, "NightFollow")
                apply_internal_follow_constraint(self.SHIFTS_LATE, self.SHIFTS_DAY + self.SHIFTS_EARLY, late_follow_config, "LateFollow")
                apply_internal_follow_constraint(self.SHIFTS_DAY, self.SHIFTS_EARLY, day_follow_config, "DayFollow")

                # 禁止連続ペア (例: 早2 -> 早1)
                for prev_s, next_s in self.forbidden_consecutive_pairs:
                    prob += (x[emp_id, d_str, prev_s] + x[emp_id, next_d_str, next_s] <= 1, f"ForbiddenPair_{prev_s}_{next_s}_{emp_id}_{d_str}")


        # --- 4. ソフト制約の定義 (動的) ---
        logging.info("Defining soft constraints.")

        # 4.1 責任者とサポの同日勤務回避
        charge_support_config = self.constraints.get('avoid_leader_and_support_same_day', {})
        if charge_support_config.get('type') == ConstraintType.SOFT:
            penalty = charge_support_config.get('penalty', 0)
            if penalty > 0:
                charge_ids = [e["id"] for e in employees_data if e["employment_type"] == EmploymentType.MANAGER]
                support_ids = [e["id"] for e in employees_data if e["employment_type"] == EmploymentType.SUPPORT]
                if charge_ids and support_ids:
                    for d_str in date_strs:
                        for c_id in charge_ids:
                            for s_id in support_ids:
                                w = pulp.LpVariable(f"cowork_{c_id}_{s_id}_{d_str}", 0, 1, pulp.LpBinary)
                                # w=1 if both are working
                                prob += w >= pulp.lpSum(x[c_id, d_str, s] for s in self.SHIFTS_WORK) + pulp.lpSum(x[s_id, d_str, s] for s in self.SHIFTS_WORK) - 1
                                objective_terms.append(w * penalty)

        # 4.2 正職員の早番/日勤確保
        main_staff_config = self.constraints.get('ensure_full_time_early_day_shift', {})
        main_staff_type = main_staff_config.get('type', ConstraintType.INACTIVE)
        if main_staff_type != ConstraintType.INACTIVE:
            full_timer_ids = [e["id"] for e in employees_data if e["employment_type"] in [EmploymentType.MANAGER, EmploymentType.SUPPORT, EmploymentType.FULL_TIME]]
            early_day_shifts = self.SHIFTS_EARLY + self.SHIFTS_DAY
            if early_day_shifts and full_timer_ids:
                for d_str in date_strs:
                    # z=1 if no main staff is working
                    z = pulp.LpVariable(f"no_main_staff_in_day_{d_str}", 0, 1, pulp.LpBinary)
                    prob += pulp.lpSum(x[emp_id, d_str, s] for emp_id in full_timer_ids for s in early_day_shifts) + z >= 1
                    prob += pulp.lpSum(x[emp_id, d_str, s] for emp_id in full_timer_ids for s in early_day_shifts) <= len(full_timer_ids) * (1 - z)
                    
                    if main_staff_type == ConstraintType.HARD:
                        prob += z == 0, f"HardEnsureMainStaff_{d_str}"
                    elif main_staff_type == ConstraintType.SOFT:
                        penalty = main_staff_config.get('penalty', 0)
                        if penalty > 0:
                            objective_terms.append(z * penalty)

        # 4.3 4連続夜勤の回避 (max_consecutive_night_shiftsが4の場合の追加ペナルティ)
        avoid_4_night_config = self.constraints.get('avoid_4_consecutive_night_shifts', {})
        night_cons_config = self.constraints.get('max_consecutive_night_shifts', {})
        if avoid_4_night_config.get('type') == ConstraintType.SOFT and night_cons_config.get('value') == 4 and self.SHIFTS_NIGHT:
            penalty = avoid_4_night_config.get('penalty', 0)
            if penalty > 0:
                for emp in employees_data:
                    for i in range(len(dates) - 3):
                        v = pulp.LpVariable(f"is_4_night_streak_{emp['id']}_{i}", 0, 1, pulp.LpBinary)
                        four_days_of_nights = pulp.lpSum(x[emp["id"], date_strs[j], s] for j in range(i, i + 4) for s in self.SHIFTS_NIGHT)
                        prob += four_days_of_nights <= 3 + v
                        objective_terms.append(v * penalty)

        # 4.4 5連続勤務の回避 (max_consecutive_workが5の場合の追加ペナルティ)
        avoid_5_work_config = self.constraints.get('avoid_5_consecutive_work_days', {})
        work_cons_config = self.constraints.get('max_consecutive_work', {})
        if avoid_5_work_config.get('type') == ConstraintType.SOFT and work_cons_config.get('value') == 5 and self.SHIFTS_WORK:
            penalty = avoid_5_work_config.get('penalty', 0)
            if penalty > 0:
                for emp in employees_data:
                    for i in range(len(dates) - 4):
                        v = pulp.LpVariable(f"is_5_work_streak_{emp['id']}_{i}", 0, 1, pulp.LpBinary)
                        five_days_of_work = pulp.lpSum(x[emp["id"], date_strs[j], s] for j in range(i, i + 5) for s in self.SHIFTS_WORK)
                        prob += five_days_of_work <= 4 + v
                        objective_terms.append(v * penalty)

        # 4.5 4連続遅番の回避 (max_consecutive_late_shiftsが4の場合の追加ペナルティ)
        avoid_4_late_config = self.constraints.get('avoid_4_consecutive_late_shifts', {})
        late_cons_config = self.constraints.get('max_consecutive_late_shifts', {})
        if avoid_4_late_config.get('type') == ConstraintType.SOFT and late_cons_config.get('value') == 4 and self.SHIFTS_LATE:
            penalty = avoid_4_late_config.get('penalty', 0)
            if penalty > 0:
                for emp in employees_data:
                    for i in range(len(dates) - 3):
                        v = pulp.LpVariable(f"is_4_late_streak_{emp['id']}_{i}", 0, 1, pulp.LpBinary)
                        four_days_of_lates = pulp.lpSum(x[emp["id"], date_strs[j], s] for j in range(i, i + 4) for s in self.SHIFTS_LATE)
                        prob += four_days_of_lates <= 3 + v
                        objective_terms.append(v * penalty)

        # 4.6 優先シフトが採用されなかった場合のペナルティ
        missed_pref_config = self.constraints.get('penalty_for_not_assigning_preferred_shift', {})
        if missed_pref_config.get('type') == ConstraintType.SOFT:
            penalty = missed_pref_config.get('penalty', 0)
            if penalty > 0:
                for emp in employees_data:
                    emp_id = emp["id"]
                    pref_1_id = emp.get("preferred_shift_1_id")
                    pref_2_id = emp.get("preferred_shift_2_id")
                    preferred_shift_names = [st.name for st_id, st in self.shift_types_by_id.items() if st_id in [pref_1_id, pref_2_id]]

                    if preferred_shift_names:
                        for d_str in date_strs:
                            is_working = pulp.lpSum(x[emp_id, d_str, s] for s in self.SHIFTS_WORK)
                            is_assigned_preferred = pulp.lpSum(x[emp_id, d_str, s] for s in preferred_shift_names)
                            # Penalize if working but not in a preferred shift
                            penalty_term = is_working - is_assigned_preferred
                            objective_terms.append(penalty_term * penalty)

        # --- 5. 目的関数設定とソルバー実行 ---
        logging.info("Solving problem...")
        prob += pulp.lpSum(objective_terms), "Objective"
        prob.writeLP("ShiftProblem.lp")  # デバッグ用
        solver = pulp.PULP_CBC_CMD(msg=True, logPath="solver.log", timeLimit=1200)
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
