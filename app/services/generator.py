import pulp
import calendar
from datetime import date, timedelta
from app import db
from app.models.user import User
from app.models.master import Role, ShiftType, ShiftConstraint
from app.models.day_off_request import DayOffRequest
from app.models.shift import ShiftAssignment

class ShiftGenerator:
    """シフト生成エンジンクラス。"""

    def __init__(self):
        # DBからマスターデータを読み込む
        self.roles = {r.role_id: r for r in db.session.query(Role).all()}
        self.shift_types = {s.name: s for s in db.session.query(ShiftType).all()}
        self.shift_types_by_id = {s.shift_type_id: s for s in self.shift_types.values()}
        self.constraints = {c.name: c.value for c in db.session.query(ShiftConstraint).all()}
        
        # --- シフトグループ定義 ---
        self.SHIFT_KYU = "休"
        self.SHIFT_MING = "明"
        self.SHIFTS_NIGHT = ["夜1", "夜2"]
        self.SHIFTS_LATE = ["遅1", "遅2"]
        self.SHIFTS_EARLY = ["早1", "早2"]
        self.SHIFTS_DAY = ["日1", "日2"]
        
        # 勤務（休み、明け以外）
        self.WORK_SHIFTS = [s for s in self.shift_types.keys() if s not in [self.SHIFT_KYU, self.SHIFT_MING]]
        # 遅番・夜勤グループ
        self.LATE_OR_NIGHT_SHIFTS = self.SHIFTS_LATE + self.SHIFTS_NIGHT
        # パート4専用シフト
        self.SHIFTS_PART4_ONLY = ["1", "2", "3", "4", "5", "6", "7", "8"]
        # パート4以外シフト
        self.SHIFTS_NON_PART4 = self.SHIFTS_EARLY + self.SHIFTS_DAY + self.SHIFTS_LATE + self.SHIFTS_NIGHT

        # --- 人員配置カウント用グループ ---
        self.GROUP_7_16 = ["早1", "早2", "日1", "日2"] + self.SHIFTS_PART4_ONLY
        self.GROUP_16_20 = ["日1", "日2", "遅1", "遅2", "8"]
        self.GROUP_20_07 = self.SHIFTS_NIGHT

    def run(self, year: int, month: int) -> tuple[bool, list | None]:
        # --- 1. データ準備 ---
        all_users = db.session.query(User).filter_by(is_admin=False).all()
        start_date = date(year, month, 1)
        num_days = calendar.monthrange(year, month)[1]
        dates = [start_date + timedelta(days=i) for i in range(num_days)]
        date_strs = [d.isoformat() for d in dates]

        day_off_reqs = {r.user_id: [d.date.isoformat() for d in r.day_off_requests] for r in all_users}
        
        employees_data = [{
            "id": u.id, "name": u.username, "role": self.roles[u.role_id], "desired_work_days": u.desired_work_days
        } for u in all_users]

        # --- 2. 問題定義 ---
        prob = pulp.LpProblem("ShiftScheduling", pulp.LpMinimize)
        x = pulp.LpVariable.dicts("x", (
            (e["id"], d, s) for e in employees_data for d in date_strs for s in self.shift_types.keys()
        ), 0, 1, pulp.LpBinary)

        objective_terms = []

        # --- 3. 制約条件の追加 ---
        for d_idx, d_str in enumerate(dates):
            current_date = dates[d_idx]
            
            # --- 3.1 人員配置 ---
            is_sunday = current_date.weekday() == 6
            if is_sunday:
                prob += pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_7_16) >= self.constraints['min_employees_sunday_7_16'], f"MinStaff_Sunday_7-16_{d_str}"
                prob += pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_16_20) >= self.constraints['min_employees_sunday_16_20'], f"MinStaff_Sunday_16-20_{d_str}"
                prob += pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_20_07) >= self.constraints['min_employees_sunday_20_07'], f"MinStaff_Sunday_20-07_{d_str}"
            else:
                prob += pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_7_16) >= self.constraints['min_employees_weekday_7_16'], f"MinStaff_Weekday_7-16_{d_str}"
                prob += pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_16_20) >= self.constraints['min_employees_weekday_16_20'], f"MinStaff_Weekday_16-20_{d_str}"
                prob += pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_20_07) >= self.constraints['min_employees_weekday_20_07'], f"MinStaff_Weekday_20-07_{d_str}"

        for emp in employees_data:
            emp_id = emp["id"]
            emp_role_name = emp["role"].name

            for d_idx, d_str in enumerate(dates):
                # --- 3.2 基本制約: 1人1日1シフト ---
                prob += pulp.lpSum(x[emp_id, d_str, s] for s in self.shift_types.keys()) == 1, f"OneShiftPerDay_{emp_id}_{d_str}"

                # --- 3.3 希望休 ---
                if d_str in day_off_reqs.get(emp_id, []):
                    prob += x[emp_id, d_str, self.SHIFT_KYU] == 1, f"DayOffRequest_{emp_id}_{d_str}"

                # --- 3.4 役割別制約 (勤務可能シフト) ---
                if emp_role_name == "パート4":
                    for s in self.SHIFTS_NON_PART4:
                        prob += x[emp_id, d_str, s] == 0, f"RoleConstraint_{emp_id}_{d_str}_{s}"
                else: # パート4以外
                    for s in self.SHIFTS_PART4_ONLY:
                        prob += x[emp_id, d_str, s] == 0, f"RoleConstraint_{emp_id}_{d_str}_{s}"
                
                if emp_role_name in ["パート2", "パート3"]:
                    for s in self.SHIFTS_NIGHT:
                        prob += x[emp_id, d_str, s] == 0, f"NoNightShift_{emp_id}_{d_str}_{s}"

                # --- 3.5 夜勤規則 ---
                if d_idx > 0:
                    prev_d_str = dates[d_idx - 1].isoformat()
                    # 夜勤の翌日は「夜勤」or「明」
                    prob += pulp.lpSum(x[emp_id, prev_d_str, s] for s in self.SHIFTS_NIGHT) <= pulp.lpSum(x[emp_id, d_str, s] for s in self.SHIFTS_NIGHT + [self.SHIFT_MING]), f"NightShiftNextDay_{emp_id}_{d_str}"
                if d_idx > 1:
                    prev_d_str = dates[d_idx - 1].isoformat()
                    # 「明」の翌日は「休」
                    prob += x[emp_id, prev_d_str, self.SHIFT_MING] <= x[emp_id, d_str, self.SHIFT_KYU], f"AkeNextDayKyu_{emp_id}_{d_str}"
            
            # --- 3.6 連続勤務 ---
            max_consecutive = self.constraints['max_consecutive_work']
            for i in range(num_days - max_consecutive):
                prob += pulp.lpSum(x[emp_id, dates[j].isoformat(), s] for j in range(i, i + max_consecutive + 1) for s in self.WORK_SHIFTS) <= max_consecutive, f"MaxConsecutiveWork_{emp_id}_{i}"
            
            max_consecutive_late_night = self.constraints['max_consecutive_late_night']
            for i in range(num_days - max_consecutive_late_night):
                 prob += pulp.lpSum(x[emp_id, dates[j].isoformat(), s] for j in range(i, i + max_consecutive_late_night + 1) for s in self.LATE_OR_NIGHT_SHIFTS) <= max_consecutive_late_night, f"MaxConsecutiveLateNight_{emp_id}_{i}"

            # --- 3.7 月間勤務日数 ---
            if emp_role_name == "介護員":
                prob += pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.WORK_SHIFTS) == self.constraints['monthly_work_days_kaigo'], f"MonthlyWorkDays_Kaigo_{emp_id}"
            
            desired_days = emp.get('desired_work_days')
            if emp_role_name.startswith("パート"):
                if desired_days is not None and desired_days > 0:
                    # 希望勤務日数が設定されていれば、それを厳守する
                    prob += pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.WORK_SHIFTS) == desired_days, f"MonthlyWorkDays_Part_{emp_id}"
                else:
                    # 設定されていなければ、希望休以外は勤務
                    for d_str in date_strs:
                        if d_str not in day_off_reqs.get(emp_id, []):
                            prob += pulp.lpSum(x[emp_id, d_str, s] for s in self.WORK_SHIFTS) == 1, f"PartTimerMustWork_{emp_id}_{d_str}"


            # --- 4. ソフト制約 (目的関数) ---
            # 介護員の夜勤回数を目標に近づける
            if emp_role_name == "介護員":
                night_shifts_total = pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_NIGHT)
                target = self.constraints['kaigo_night_shift_target']
                # 目標との差の絶対値をペナルティにする (線形化)
                delta = pulp.LpVariable(f"night_delta_{emp_id}", 0, None)
                prob += night_shifts_total - target <= delta
                prob += target - night_shifts_total <= delta
                objective_terms.append(delta * self.constraints['weight_kaigo_night_shift_target'])

            # 役割ごとの優先シフト
            if emp_role_name == "パート1":
                objective_terms.append(-1 * self.constraints['weight_part1_night_shift'] * pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_NIGHT))
            if emp_role_name == "パート2":
                objective_terms.append(-1 * self.constraints['weight_part2_late_shift'] * pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_LATE))
            if emp_role_name == "責任者" or emp_role_name == "サポート":
                 objective_terms.append(-1 * self.constraints['weight_leader_support_early_shift'] * pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_EARLY))
            
            # 連続勤務日数の短縮化
            objective_terms.append(self.constraints['weight_minimize_consecutive_work'] * pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.WORK_SHIFTS))
        
        # 責任者とサポートの同日勤務回避
        leader_ids = [e['id'] for e in employees_data if e['role'].name == '責任者']
        support_ids = [e['id'] for e in employees_data if e['role'].name == 'サポート']
        for d_str in date_strs:
            for l_id in leader_ids:
                for s_id in support_ids:
                    # w = 1 if both work, 0 otherwise
                    w = pulp.LpVariable(f"cowork_{l_id}_{s_id}_{d_str}", 0, 1, pulp.LpBinary)
                    # w >= x_l + x_s - 1
                    prob += w >= pulp.lpSum(x[l_id, d_str, s] for s in self.WORK_SHIFTS) + pulp.lpSum(x[s_id, d_str, s] for s in self.WORK_SHIFTS) - 1
                    objective_terms.append(w * self.constraints['weight_avoid_leader_support_same_day'])

        # --- 5. 目的関数設定とソルバー実行 ---
        prob += pulp.lpSum(objective_terms), "Objective"
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

        if status not in [pulp.LpStatusOptimal, pulp.LpStatusFeasible]:
            print("Shift generation failed: Infeasible or Unbounded")
            # You can uncomment the line below to write the LP problem to a file for debugging
            # prob.writeLP("ShiftProblem.lp")
            return False, None

        # --- 6. 結果のDB保存 & PDF用データ作成 ---
        try:
            db.session.query(ShiftAssignment).filter(
                ShiftAssignment.date.between(start_date, dates[-1])
            ).delete()

            assignments_to_add = []
            assignments_for_pdf = []
            for emp in employees_data:
                for d_str in date_strs:
                    for s_name in self.shift_types.keys():
                        if pulp.value(x[emp["id"], d_str, s_name]) == 1:
                            assignments_to_add.append(ShiftAssignment(
                                date=date.fromisoformat(d_str),
                                user_id=emp["id"],
                                shift_type_id=self.shift_types[s_name].shift_type_id,
                            ))
                            assignments_for_pdf.append({
                                "date": d_str, "employee_id": emp["id"], "shift_type": s_name
                            })
                            break
            
            db.session.bulk_save_objects(assignments_to_add)
            db.session.commit()
            return True, assignments_for_pdf
        except Exception as e:
            db.session.rollback()
            print(f"Error saving assignments to DB: {e}")
            return False, None