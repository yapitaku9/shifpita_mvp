import pulp
import calendar
from datetime import date, timedelta, time
from app import db
from app.models.user import User, EmploymentType
from app.models.master import ShiftType, ShiftConstraint
from app.models.day_off_request import DayOffRequest
from app.models.work_request import WorkRequest
from app.models.desired_work_days_request import DesiredWorkDaysRequest
from app.models.shift import ShiftAssignment
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
        self.SHIFT_AKE = "明" # '明'は '夜勤明け' の意

        self.SHIFTS_NIGHT = [st.name for st in self.shift_types_by_id.values() if st.is_night_shift]
        self.SHIFTS_LATE = [st.name for st in self.shift_types_by_id.values() if st.category == '遅番']
        self.SHIFTS_EARLY = [st.name for st in self.shift_types_by_id.values() if st.category == '早番']
        self.SHIFTS_DAY = [st.name for st in self.shift_types_by_id.values() if st.category == '日勤']
        
        # 勤務（休み、明け以外）
        self.SHIFTS_WORK = [s.name for s in self.shift_types_by_id.values() if s.name not in [self.SHIFT_KYU, self.SHIFT_AKE]]
        # 正社員の勤務シフト
        self.SHIFTS_FULL_TIME_WORK = [s for s in self.SHIFTS_WORK if s not in ['1','2','3','4','5','6','7','8']]
        # 遅番または夜勤
        self.SHIFTS_LATE_OR_NIGHT = self.SHIFTS_LATE + self.SHIFTS_NIGHT
        
        # --- 時間帯別人員配置のためのグループ ---
        self.hourly_groups = {h: [] for h in range(24)}
        for st in self.shift_types_by_id.values():
            if not st.start_time or not st.end_time:
                continue
            
            start_h = st.start_time.hour
            end_h = st.end_time.hour
            
            if start_h < end_h: # 日中シフト
                for h in range(start_h, end_h):
                    self.hourly_groups[h].append(st.name)
            else: # 夜勤など日をまたぐシフト
                for h in range(start_h, 24):
                    self.hourly_groups[h].append(st.name)
                for h in range(0, end_h):
                    self.hourly_groups[h].append(st.name)


    def run(self, year: int, month: int) -> tuple[bool, list | str | None]:
        # --- 1. データ準備 ---
        all_users = db.session.query(User).filter_by(is_admin=False).all()
        start_date = date(year, month, 1)
        end_date = date(year, month, calendar.monthrange(year, month)[1])
        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        date_strs = [d.isoformat() for d in dates]

        # 承認済みの希望休を取得
        day_off_reqs = {}
        approved_day_offs = DayOffRequest.query.filter(
            DayOffRequest.date.between(start_date, end_date), DayOffRequest.status == "approved"
        ).all()
        for req in approved_day_offs:
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

        # 承認済みの希望勤務日数を取得
        dwd_req_map = {}
        approved_dwd_reqs = DesiredWorkDaysRequest.query.filter_by(year=year, month=month, status='approved').all()
        for req in approved_dwd_reqs:
            dwd_req_map[req.user_id] = {'min': req.min_days, 'max': req.max_days}

        # 特別日を取得
        special_days_map = {sd.date.isoformat(): sd for sd in SpecialDay.query.filter(
            SpecialDay.date.between(start_date, end_date)
        ).all()}

        employees_data = [
            {
                "id": u.id,
                "name": u.full_name,
                "employment_type": u.employment_type,
                "max_consecutive_work_days": u.max_consecutive_work_days,
                "preferred_night_shifts": u.preferred_night_shifts,
                "min_work_days": dwd_req_map.get(u.id, {}).get('min'),
                "max_work_days": dwd_req_map.get(u.id, {}).get('max'),
                "preferred_shift_1_id": u.preferred_shift_1_id,
                "preferred_shift_2_id": u.preferred_shift_2_id,
            }
            for u in all_users
        ]

        # --- 2. 問題定義 ---
        prob = pulp.LpProblem("ShiftScheduling", pulp.LpMinimize)
        x = pulp.LpVariable.dicts(
            "x",
            ((e["id"], d, s) for e in employees_data for d in date_strs for s in self.shift_types_by_name.keys()),
            0,
            1,
            pulp.LpBinary,
        )
        objective_terms = []

        # --- 3. ハード制約の追加 ---
        
        # 3.1 1人1日1シフト
        for emp in employees_data:
            for d_str in date_strs:
                prob += (pulp.lpSum(x[emp["id"], d_str, s] for s in self.shift_types_by_name.keys()) == 1, f"OneShiftPerDay_{emp['id']}_{d_str}")

        # 3.2 希望休・希望勤務
        for emp in employees_data:
            for d_str in date_strs:
                # 希望休
                if d_str in day_off_reqs.get(emp["id"], []):
                    prob += (x[emp["id"], d_str, self.SHIFT_KYU] == 1, f"DayOffRequest_{emp['id']}_{d_str}")
                # 希望勤務
                if (emp["id"], d_str) in work_req_map:
                    requested_shifts = work_req_map[(emp["id"], d_str)]
                    prob += (pulp.lpSum(x[emp["id"], d_str, s] for s in requested_shifts) == 1, f"WorkRequest_{emp['id']}_{d_str}")

        # 3.3 人員配置基準（ハード制約）と超過ペナルティ（ソフト制約）
        # 超過ペナルティの重みを取得
        p1 = self.constraints.get("weight_exceed_staffing_1", 10)
        p2 = self.constraints.get("weight_exceed_staffing_2", 30)
        p3_plus = self.constraints.get("weight_exceed_staffing_3_plus", 100)

        hourly_req_keys = [
            '0700', '0800', '0900', '1200', '1300', '1400', 
            '1600', '1800', '1900', '2000_next_0700'
        ]
        for d_idx, d_str in enumerate(date_strs):
            current_date = date.fromisoformat(d_str)
            is_sunday = current_date.weekday() == 6
            day_type = "sunday" if is_sunday else "weekday"
            
            special_day_info = special_days_map.get(d_str)
            staff_increase = special_day_info.staff_increase if special_day_info else 0

            for key in hourly_req_keys:
                hour = int(key.split('_')[0])
                # 20時-7時は夜勤グループで判定
                if hour == 20:
                    req_staff_count = self.constraints.get(f"min_staff_{day_type}_2000_next_0700", 2)
                    shifts_for_hour = self.SHIFTS_NIGHT
                else:
                    req_staff_count = self.constraints.get(f"min_staff_{day_type}_{key}", 0)
                    shifts_for_hour = self.hourly_groups.get(hour, [])

                if shifts_for_hour:
                    # 実際の配置人数
                    actual_staff = pulp.lpSum(x[emp["id"], d_str, s] for emp in employees_data for s in shifts_for_hour)
                    
                    # ハード制約: 最低必要人数を必ず満たす
                    prob += actual_staff >= req_staff_count + staff_increase, f"MinStaff_{day_type}_{key}_{d_str}"

                    # ソフト制約: 超過人数ペナルティ
                    over_staff = pulp.LpVariable(f"OverStaff_{d_str}_{key}", 0, None, pulp.LpInteger)
                    prob += over_staff == actual_staff - (req_staff_count + staff_increase), f"OverStaff_Def_{d_str}_{key}"
                    
                    # 超過レベルを示すバイナリ変数
                    is_1_or_more = pulp.LpVariable(f"is_1_or_more_{d_str}_{key}", 0, 1, pulp.LpBinary)
                    is_2_or_more = pulp.LpVariable(f"is_2_or_more_{d_str}_{key}", 0, 1, pulp.LpBinary)
                    is_3_or_more = pulp.LpVariable(f"is_3_or_more_{d_str}_{key}", 0, 1, pulp.LpBinary)

                    # over_staff変数とバイナリ変数をリンクさせる制約
                    max_staff = len(employees_data)
                    prob += over_staff <= max_staff * is_1_or_more
                    prob += over_staff >= is_1_or_more

                    prob += over_staff - 1 <= (max_staff - 1) * is_2_or_more
                    prob += over_staff - 1 >= is_2_or_more -1 # over_staff >= is_2_or_more

                    prob += over_staff - 2 <= (max_staff - 2) * is_3_or_more
                    prob += over_staff - 2 >= is_3_or_more - 1 # over_staff -1 >= is_3_or_more

                    # 目的関数に段階的ペナルティを追加
                    penalty_expr = p1 * (is_1_or_more - is_2_or_more) + \
                                   p2 * (is_2_or_more - is_3_or_more) + \
                                   p3_plus * is_3_or_more
                    
                    objective_terms.append(penalty_expr)

        for emp in employees_data:
            emp_id = emp["id"]
            
            # 3.4 勤務日数 (最低・最大)
            min_days = emp.get("min_work_days")
            max_days = emp.get("max_work_days")
            if min_days is not None:
                prob += (pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_WORK) >= min_days, f"MinWorkDays_{emp_id}")
            if max_days is not None:
                prob += (pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_WORK) <= max_days, f"MaxWorkDays_{emp_id}")

            # 3.5 夜勤希望回数
            pref_night_shifts = emp.get("preferred_night_shifts")
            if pref_night_shifts is not None:
                prob += (pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_NIGHT) == pref_night_shifts, f"PreferredNightShifts_{emp_id}")

            # 3.6 連勤制約
            # 最大連勤日数 (全体)
            max_consecutive = emp.get("max_consecutive_work_days") or self.constraints.get("max_consecutive_work_days", 5)
            for i in range(len(dates) - max_consecutive):
                prob += (pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i, i + max_consecutive + 1) for s in self.SHIFTS_WORK) <= max_consecutive, f"MaxConsecutiveWork_{emp_id}_{i}")
            
            # 夜勤の最大連勤日数
            max_consecutive_night = int(self.constraints.get("max_consecutive_night_shifts", 4))
            for i in range(len(dates) - max_consecutive_night):
                 prob += (pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i, i + max_consecutive_night + 1) for s in self.SHIFTS_NIGHT) <= max_consecutive_night, f"MaxConsecutiveNight_{emp_id}_{i}")

            # 遅番・夜勤の最大連勤日数
            max_consecutive_late_night = int(self.constraints.get("max_consecutive_late_and_night", 4))
            for i in range(len(dates) - max_consecutive_late_night):
                prob += (pulp.lpSum(x[emp_id, date_strs[j], s] for j in range(i, i + max_consecutive_late_night + 1) for s in self.SHIFTS_LATE_OR_NIGHT) <= max_consecutive_late_night, f"MaxConsecutiveLateNight_{emp_id}_{i}")

            # 3.7 シフト構成ルール
            is_full_timer = emp["employment_type"] in [EmploymentType.MANAGER, EmploymentType.SUPPORT, EmploymentType.FULL_TIME]
            
            for d_idx, d_str in enumerate(date_strs):
                # 夜勤の翌日は「明」 or 「夜勤」
                if d_idx > 0:
                    prev_d_str = date_strs[d_idx-1]
                    for night_shift in self.SHIFTS_NIGHT:
                        prob += (x[emp_id, prev_d_str, night_shift] <= pulp.lpSum(x[emp_id, d_str, s] for s in [self.SHIFT_AKE] + self.SHIFTS_NIGHT), f"NightMustBeFollowedByAkeOrNight_{emp_id}_{prev_d_str}_{night_shift}")
                # 「明」は夜勤の翌日のみ
                if d_idx > 0:
                    prev_d_str = date_strs[d_idx-1]
                    prob += (x[emp_id, d_str, self.SHIFT_AKE] <= pulp.lpSum(x[emp_id, prev_d_str, s] for s in self.SHIFTS_NIGHT), f"AkeOnlyAfterNight_{emp_id}_{d_str}")
                else: # 月初は明不可
                    prob += (x[emp_id, d_str, self.SHIFT_AKE] == 0, f"NoAkeOnFirstDay_{emp_id}")

                if d_idx < len(dates) - 1:
                    next_d_str = date_strs[d_idx + 1]
                    
                    # 明けの翌日は休み
                    if self.constraints.get("require_day_off_after_ake", 1) == 1:
                        prob += (x[emp_id, d_str, self.SHIFT_AKE] <= x[emp_id, next_d_str, self.SHIFT_KYU], f"RestAfterAke_{emp_id}_{d_str}")

                    # 正職員の連続シフト制約
                    if is_full_timer:
                        # 夜勤の翌日に禁止のシフト
                        if self.constraints.get("disallow_specific_shifts_after_night", 1) == 1:
                            forbidden_shifts = self.SHIFTS_LATE + self.SHIFTS_DAY + self.SHIFTS_EARLY
                            for night_shift in self.SHIFTS_NIGHT:
                                for forbidden_shift in forbidden_shifts:
                                    prob += x[emp_id, d_str, night_shift] + x[emp_id, next_d_str, forbidden_shift] <= 1, f"No_{forbidden_shift}_After_{night_shift}_{emp_id}_{d_str}"
                        
                        # 遅番の翌日に禁止のシフト
                        if self.constraints.get("disallow_specific_shifts_after_late", 1) == 1:
                            forbidden_shifts = self.SHIFTS_DAY + self.SHIFTS_EARLY
                            for late_shift in self.SHIFTS_LATE:
                                for forbidden_shift in forbidden_shifts:
                                     prob += x[emp_id, d_str, late_shift] + x[emp_id, next_d_str, forbidden_shift] <= 1, f"No_{forbidden_shift}_After_{late_shift}_{emp_id}_{d_str}"

                        # 日勤の翌日に禁止のシフト
                        if self.constraints.get("disallow_specific_shifts_after_day", 1) == 1:
                            forbidden_shifts = self.SHIFTS_EARLY
                            for day_shift in self.SHIFTS_DAY:
                                for forbidden_shift in forbidden_shifts:
                                     prob += x[emp_id, d_str, day_shift] + x[emp_id, next_d_str, forbidden_shift] <= 1, f"No_{forbidden_shift}_After_{day_shift}_{emp_id}_{d_str}"
        

        # --- 4. ソフト制約 (目的関数) の追加 ---

        # 4.4 人員配置の超過ペナルティ (重み: 最大)
        # Note: これはハード制約で `>=` としているため、超過を許容しつつペナルティを課す形にする
        # Surplus変数を各人員配置制約に追加する
        exceed_staffing_weight = self.constraints.get("weight_exceed_staffing", 1000) # 仮の重み
        
        # 4.1 責任者とサポの同日勤務回避 (重み: 最小)
        if self.constraints.get("avoid_charge_and_support_same_day", 1) == 1:
            charge_ids = [e["id"] for e in employees_data if e["employment_type"] == EmploymentType.MANAGER]
            support_ids = [e["id"] for e in employees_data if e["employment_type"] == EmploymentType.SUPPORT]
            weight = self.constraints.get("weight_avoid_charge_support", 1) # 仮の重み
            for d_str in date_strs:
                for c_id in charge_ids:
                    for s_id in support_ids:
                        # c_idとs_idが同日に勤務している場合に1になる変数
                        w = pulp.LpVariable(f"cowork_{c_id}_{s_id}_{d_str}", 0, 1, pulp.LpBinary)
                        is_c_working = pulp.lpSum(x[c_id, d_str, s] for s in self.SHIFTS_WORK)
                        is_s_working = pulp.lpSum(x[s_id, d_str, s] for s in self.SHIFTS_WORK)
                        prob += w >= is_c_working + is_s_working - 1
                        objective_terms.append(w * weight)

        # 4.2 正職員の早番/日勤確保 (重み: 中)
        if self.constraints.get("ensure_main_staff_in_day_shift", 1) == 1:
            full_timer_ids = [e["id"] for e in employees_data if e["employment_type"] in [EmploymentType.MANAGER, EmploymentType.SUPPORT, EmploymentType.FULL_TIME]]
            early_day_shifts = self.SHIFTS_EARLY + self.SHIFTS_DAY
            weight = self.constraints.get("weight_ensure_main_staff", 50) # 仮の重み
            for d_str in date_strs:
                # その日に正職員が早番/日勤にいない場合に1になる変数
                z = pulp.LpVariable(f"no_main_staff_in_day_{d_str}", 0, 1, pulp.LpBinary)
                prob += pulp.lpSum(x[emp_id, d_str, s] for emp_id in full_timer_ids for s in early_day_shifts) + z >= 1
                prob += pulp.lpSum(x[emp_id, d_str, s] for emp_id in full_timer_ids for s in early_day_shifts) <= len(full_timer_ids) * (1 - z)
                objective_terms.append(z * weight)

        # 4.3 4連続夜勤の回避 (重み: 小)
        max_consecutive_night = int(self.constraints.get("max_consecutive_night_shifts", 4))
        if max_consecutive_night == 4: # ハード制約が4日の場合、4日目にペナルティ
            weight = self.constraints.get("weight_avoid_4_night_streak", 10) # 仮の重み
            for emp in employees_data:
                for i in range(len(dates) - 3):
                    # 4連勤した場合に1になる変数
                    v = pulp.LpVariable(f"is_4_night_streak_{emp['id']}_{i}", 0, 1, pulp.LpBinary)
                    four_days_of_nights = pulp.lpSum(x[emp['id'], date_strs[j], s] for j in range(i, i + 4) for s in self.SHIFTS_NIGHT)
                    prob += four_days_of_nights <= 3 + v # 4になるとv=1を強制
                    objective_terms.append(v * weight)

        # 4.5 優先シフトが採用されなかった場合のペナルティ(勤務日)
        weight = self.constraints.get("penalty_missed_preferred_shift", 10)
        for emp in employees_data:
            emp_id = emp["id"]
            pref_1_id = emp.get("preferred_shift_1_id")
            pref_2_id = emp.get("preferred_shift_2_id")

            preferred_shift_names = []
            if pref_1_id:
                preferred_shift_names.append(self.shift_types_by_id[pref_1_id].name)
            if pref_2_id and pref_2_id != pref_1_id: # 重複を避ける
                preferred_shift_names.append(self.shift_types_by_id[pref_2_id].name)

            if preferred_shift_names:
                for d_str in date_strs:
                    is_working = pulp.lpSum(x[emp_id, d_str, s] for s in self.SHIFTS_WORK)
                    is_assigned_any_preferred = pulp.lpSum(x[emp_id, d_str, s] for s in preferred_shift_names)
                    
                    # Penalize if working but not in any of the preferred shifts
                    penalty_term = is_working - is_assigned_any_preferred
                    objective_terms.append(penalty_term * weight)



        # --- 5. 目的関数設定とソルバー実行 ---
        prob += pulp.lpSum(objective_terms), "Objective"
        # prob.writeLP("ShiftProblem.lp") # デバッグ用
        solver = pulp.PULP_CBC_CMD(msg=True, logPath="solver.log")
        status = prob.solve(solver)

        if status not in [pulp.LpStatusOptimal]:
            prob.writeLP("ShiftProblem.lp")
            error_message = f"シフト生成に失敗しました。解が見つかりませんでした (Status: {pulp.LpStatus[status]})"
            return False, error_message

        # --- 6. 結果のDB保存 & PDF用データ作成 ---
        try:
            db.session.query(ShiftAssignment).filter(
                ShiftAssignment.date.between(start_date, dates[-1])
            ).delete()

            assignments_to_add = []
            assignments_for_pdf = []
            for emp in employees_data:
                for d_str in date_strs:
                    for s_name in self.shift_types_by_name.keys():
                        if pulp.value(x[emp["id"], d_str, s_name]) == 1:
                            assignments_to_add.append(
                                ShiftAssignment(
                                    date=date.fromisoformat(d_str),
                                    user_id=emp["id"],
                                    shift_type_id=self.shift_types_by_name[s_name].shift_type_id,
                                )
                            )
                            assignments_for_pdf.append(
                                {"date": d_str, "employee_id": emp["id"], "shift_type": s_name}
                            )
                            break

            db.session.bulk_save_objects(assignments_to_add)
            db.session.commit()
            return True, assignments_for_pdf
        except Exception as e:
            db.session.rollback()
            return False, f"シフト結果のDB保存中にエラーが発生しました: {e}"
