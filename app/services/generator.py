import pulp
import calendar
from datetime import date, timedelta
from app import db
from app.models.user import User
from app.models.master import Role, ShiftType, ShiftConstraint
from app.models.day_off_request import DayOffRequest
from app.models.work_request import WorkRequest
from app.models.shift import ShiftAssignment
from app.models.special_day import SpecialDay


class ShiftGenerator:
    """シフト生成エンジンクラス。"""

    def __init__(self):
<<<<<<< HEAD
        # シフトタイプの定義（簡易版）
        # 実際はDBから取得するか、引数で受け取る
        self.shift_types = ["早1", "早2", "日1", "日2", "遅1", "遅2", "夜1", "夜2", "明", "休"]

    def run(
        self, year: int, month: int, employees: list, special_days: list, enabled_constraints: list = None
    ) -> list:
        """シフト生成を実行します。

        Args:
            year (int): 年
            month (int): 月
            employees (list): 従業員リスト [{'id': 1, 'name': '...', 'role_id': 1, 'day_off_requests': ['2026-10-01']}, ...]
<<<<<<< HEAD
            special_days (list): 特別日リスト [{'date': '2026-10-20', 'additional_staff_count': 1}, ...]
            enabled_constraints (list, optional): 有効にする制約のキーリスト。Noneの場合は全制約を有効化。
=======
            special_days (list): 特別日リスト
>>>>>>> parent of ac489dc (だいぶ良さそうだけど、２１日の勤務日数が守られていないぞ！)

        Returns:
            list: 生成されたシフト割当 [{'date': 'YYYY-MM-DD', 'employee_id': 1, 'shift_type': '早1'}, ...]
        """

        # 1. 日付リストの作成
        num_days = calendar.monthrange(year, month)[1]
        dates = [date(year, month, day) for day in range(1, num_days + 1)]
        date_strs = [d.isoformat() for d in dates]

<<<<<<< HEAD
        # 特別日のマッピング {date_str: additional_count}
        special_day_map = {sd["date"]: sd.get("additional_staff_count", 0) for sd in special_days}
=======
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
        end_date = date(year, month, calendar.monthrange(year, month)[1])
        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        date_strs = [d.isoformat() for d in dates]

        day_off_reqs = {r.id: [d.date.isoformat() for d in r.day_off_requests] for r in all_users}
>>>>>>> feature

        # 承認済みの希望勤務を取得し、(user_id, date) をキーとする辞書を作成
        approved_work_reqs = WorkRequest.query.filter(
            WorkRequest.date.between(start_date, end_date),
            WorkRequest.status == 'approved'
        ).all()
        work_req_map = {}
        for req in approved_work_reqs:
            key = (req.user_id, req.date.isoformat())
            work_req_map[key] = req.shift_type_id
        
        # 特別日を取得
        special_days_query = SpecialDay.query.filter(
            SpecialDay.date >= start_date,
            SpecialDay.date <= end_date
        ).all()
        special_days_map = {sd.date: sd for sd in special_days_query}

<<<<<<< HEAD
=======
>>>>>>> parent of ac489dc (だいぶ良さそうだけど、２１日の勤務日数が守られていないぞ！)
        # 2. 問題の定義
=======

        employees_data = [
            {
                "id": u.id,
                "name": u.username,
                "role": self.roles[u.role_id],
                "desired_work_days": u.desired_work_days,
                "workable_shift_ids": {s.shift_type_id for s in u.workable_shifts}
            }
            for u in all_users
        ]

        # --- 2. 問題定義 ---
>>>>>>> feature
        prob = pulp.LpProblem("ShiftScheduling", pulp.LpMinimize)
        x = pulp.LpVariable.dicts(
            "x",
            ((e["id"], d, s) for e in employees_data for d in date_strs for s in self.shift_types.keys()),
            0,
            1,
            pulp.LpBinary,
        )

<<<<<<< HEAD
        # 3. 変数の定義
        # x[employee_id, date_str, shift_type] = 0 or 1
        x = {}
        for emp in employees:
            for d in date_strs:
                for s in self.shift_types:
                    x[emp["id"], d, s] = pulp.LpVariable(f"x_{emp['id']}_{d}_{s}", 0, 1, pulp.LpBinary)
=======
        objective_terms = []

        # --- 3. 制約条件の追加 ---
        for d_idx, d_str in enumerate(date_strs):
            current_date = date.fromisoformat(d_str)
>>>>>>> feature

            # --- 3.1 人員配置 ---
            # その日の特別日設定を取得
            special_day_info = special_days_map.get(current_date)
            staff_increase_7_16 = special_day_info.staff_increase if special_day_info else 0

<<<<<<< HEAD
        # (1) 各従業員は1日につき必ず1つのシフト（または休み）が入る
        for emp in employees:
            for d in date_strs:
                prob += pulp.lpSum([x[emp["id"], d, s] for s in self.shift_types]) == 1

<<<<<<< HEAD
        # --- 役割別シフト制限 (ハード制約) ---
        if "hard_role_restrictions" in enabled_constraints:
            for emp in employees:
                role_id = emp["role_id"]
=======
            is_sunday = current_date.weekday() == 6
            if is_sunday:
                prob += (
                    pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_7_16)
                    >= self.constraints["min_employees_sunday_7_16"] + staff_increase_7_16,
                    f"MinStaff_Sunday_7-16_{d_str}",
                )
                prob += (
                    pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_16_20)
                    >= self.constraints["min_employees_sunday_16_20"],
                    f"MinStaff_Sunday_16-20_{d_str}",
                )
                prob += (
                    pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_20_07)
                    >= self.constraints["min_employees_sunday_20_07"],
                    f"MinStaff_Sunday_20-07_{d_str}",
                )
            else:
                prob += (
                    pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_7_16)
                    >= self.constraints["min_employees_weekday_7_16"] + staff_increase_7_16,
                    f"MinStaff_Weekday_7-16_{d_str}",
                )
                prob += (
                    pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_16_20)
                    >= self.constraints["min_employees_weekday_16_20"],
                    f"MinStaff_Weekday_16-20_{d_str}",
                )
                prob += (
                    pulp.lpSum(x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_20_07)
                    >= self.constraints["min_employees_weekday_20_07"],
                    f"MinStaff_Weekday_20-07_{d_str}",
                )

        for emp in employees_data:
            emp_id = emp["id"]
            emp_role_name = emp["role"].name
>>>>>>> feature

            for d_idx, d_str in enumerate(date_strs):
                # --- 3.2 基本制約: 1人1日1シフト ---
                prob += (
                    pulp.lpSum(x[emp_id, d_str, s] for s in self.shift_types.keys()) == 1,
                    f"OneShiftPerDay_{emp_id}_{d_str}",
                )

                # --- 3.3 希望休 ---
                if d_str in day_off_reqs.get(emp_id, []):
                    prob += x[emp_id, d_str, self.SHIFT_KYU] == 1, f"DayOffRequest_{emp_id}_{d_str}"
                
                # --- 3.3.1 希望勤務 (ハード制約) ---
                work_req_key = (emp_id, d_str)
                if work_req_key in work_req_map:
                    shift_id = work_req_map[work_req_key]
                    shift_name = self.shift_types_by_id[shift_id].name
                    prob += x[emp_id, d_str, shift_name] == 1, f"WorkRequest_{emp_id}_{d_str}"

                # --- 3.4 役割別制約 (勤務可能シフト) ---
                if emp_role_name == "パート4":
                    # パート4は、許可されていないシフトには入れない
                    allowed_shift_ids = emp["workable_shift_ids"]
                    all_part4_shift_ids = {st.shift_type_id for st in self.shift_types.values() if st.name in self.SHIFTS_PART4_ONLY}
                    
                    forbidden_shift_ids = all_part4_shift_ids - allowed_shift_ids
                    for shift_id in forbidden_shift_ids:
                        shift_name = self.shift_types_by_id[shift_id].name
                        prob += x[emp_id, d_str, shift_name] == 0, f"Part4_ForbiddenShift_{emp_id}_{d_str}_{shift_name}"
                    
                    # パート4は、パート4以外のシフトには入れない (既存のルール)
                    for s in self.SHIFTS_NON_PART4:
                        prob += x[emp_id, d_str, s] == 0, f"RoleConstraint_NonPart4_{emp_id}_{d_str}_{s}"
                else:  # パート4以外
                    for s in self.SHIFTS_PART4_ONLY:
                        prob += x[emp_id, d_str, s] == 0, f"RoleConstraint_Part4Only_{emp_id}_{d_str}_{s}"

                if emp_role_name in ["パート2", "パート3"]:
                    for s in self.SHIFTS_NIGHT:
                        prob += x[emp_id, d_str, s] == 0, f"NoNightShift_{emp_id}_{d_str}_{s}"

                # 夜勤ができない、または夜勤をしない役割は「明」シフトにもなれない
                if emp_role_name in ["パート2", "パート3", "パート4"]:
                    prob += x[emp_id, d_str, self.SHIFT_MING] == 0, f"NoAkeForRole_{emp_id}_{d_str}"

                # --- 3.5 夜勤規則 ---
                # 「明」の翌日は「休」
                if d_idx < len(dates) - 1:
                    next_d_str = date_strs[d_idx + 1]
                    prob += (
                        x[emp_id, d_str, self.SHIFT_MING] <= x[emp_id, next_d_str, self.SHIFT_KYU],
                        f"AkeNextDayKyu_{emp_id}_{d_str}",
                    )

                if d_idx > 0:
                    prev_d_str = date_strs[d_idx - 1]
                    # 夜勤の翌日は「夜勤」or「明」
                    prob += (
                        pulp.lpSum(x[emp_id, prev_d_str, s] for s in self.SHIFTS_NIGHT)
                        <= pulp.lpSum(x[emp_id, d_str, s] for s in self.SHIFTS_NIGHT + [self.SHIFT_MING]),
                        f"NightShiftNextDay_{emp_id}_{d_str}",
                    )
                    # 「明」シフトは前日が夜勤の場合のみ
                    prob += (
                        x[emp_id, d_str, self.SHIFT_MING]
                        <= pulp.lpSum(x[emp_id, prev_d_str, s] for s in self.SHIFTS_NIGHT),
                        f"AkeOnlyAfterNight_{emp_id}_{d_str}",
                    )
                else:  # 初日
                    # 初日は「明」になれない
                    prob += x[emp_id, d_str, self.SHIFT_MING] == 0, f"NoAkeOnFirstDay_{emp_id}"

            # --- 3.6 連続勤務 ---
            max_consecutive = self.constraints["max_consecutive_work"]
            for i in range(len(dates) - max_consecutive):
                prob += (
                    pulp.lpSum(
                        x[emp_id, dates[j].isoformat(), s]
                        for j in range(i, i + max_consecutive + 1)
                        for s in self.WORK_SHIFTS
                    )
                    <= max_consecutive,
                    f"MaxConsecutiveWork_{emp_id}_{i}",
                )

            max_consecutive_late_night = self.constraints["max_consecutive_late_night"]
            for i in range(len(dates) - max_consecutive_late_night):
                prob += (
                    pulp.lpSum(
                        x[emp_id, dates[j].isoformat(), s]
                        for j in range(i, i + max_consecutive_late_night + 1)
                        for s in self.LATE_OR_NIGHT_SHIFTS
                    )
                    <= max_consecutive_late_night,
                    f"MaxConsecutiveLateNight_{emp_id}_{i}",
                )

            # --- 3.7 月間勤務日数 ---
            if emp_role_name in ["介護員", "責任者", "サポート"]:
                prob += (
                    pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.WORK_SHIFTS)
                    == self.constraints["monthly_work_days_kaigo"],
                    f"MonthlyWorkDays_HardConstraint_{emp_id}",
                )

            # --- パートの月間シフト回数上限 ---
            if emp_role_name == "パート1":
                prob += (
                    pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_NIGHT)
                    <= self.constraints["max_part1_night_shifts"],
                    f"MaxPart1NightShifts_{emp_id}",
                )
            if emp_role_name == "パート2":
                prob += (
                    pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_LATE)
                    <= self.constraints["max_part2_late_shifts"],
                    f"MaxPart2LateShifts_{emp_id}",
                )
            if emp_role_name == "パート3":
                prob += (
                    pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_LATE)
                    <= self.constraints.get("max_part3_late_shifts", 6),
                    f"MaxPart3LateShifts_{emp_id}",
                )

            desired_days = emp.get("desired_work_days")
            if emp_role_name.startswith("パート"):
                if desired_days is not None and desired_days > 0:
                    # 希望勤務日数が設定されていれば、それを厳守する
                    prob += (
                        pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.WORK_SHIFTS)
                        == desired_days,
                        f"MonthlyWorkDays_Part_{emp_id}",
                    )
                else:
                    # 設定されていなければ、希望休以外は勤務
                    for d_str in date_strs:
                        if d_str not in day_off_reqs.get(emp_id, []):
                            prob += (
                                pulp.lpSum(x[emp_id, d_str, s] for s in self.WORK_SHIFTS) == 1,
                                f"PartTimerMustWork_{emp_id}_{d_str}",
                            )

            # --- 4. ソフト制約 (目的関数) ---
            # 介護員の夜勤回数を目標に近づける
            if emp_role_name == "介護員":
                night_shifts_total = pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_NIGHT)
                target = self.constraints["kaigo_night_shift_target"]
                # 目標との差の絶対値をペナルティにする (線形化)
                delta = pulp.LpVariable(f"night_delta_{emp_id}", 0, None)
                prob += night_shifts_total - target <= delta
                prob += target - night_shifts_total <= delta
                objective_terms.append(delta * self.constraints["weight_kaigo_night_shift_target"])

            # 役割ごとの優先シフト
            if emp_role_name == "責任者" or emp_role_name == "サポート":
                objective_terms.append(
                    -1
                    * self.constraints["weight_leader_support_early_shift"]
                    * pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.SHIFTS_EARLY + self.SHIFTS_DAY)
                )

            # 連続勤務日数の短縮化
            objective_terms.append(
                self.constraints["weight_minimize_consecutive_work"]
                * pulp.lpSum(x[emp_id, d, s] for d in date_strs for s in self.WORK_SHIFTS)
            )

        # 責任者とサポートの同日勤務回避
        leader_ids = [e["id"] for e in employees_data if e["role"].name == "責任者"]
        support_ids = [e["id"] for e in employees_data if e["role"].name == "サポート"]
        for d_str in date_strs:
            for l_id in leader_ids:
                for s_id in support_ids:
                    # w = 1 if both work, 0 otherwise
                    w = pulp.LpVariable(f"cowork_{l_id}_{s_id}_{d_str}", 0, 1, pulp.LpBinary)
                    # w >= x_l + x_s - 1
                    prob += (
                        w
                        >= pulp.lpSum(x[l_id, d_str, s] for s in self.WORK_SHIFTS)
                        + pulp.lpSum(x[s_id, d_str, s] for s in self.WORK_SHIFTS)
                        - 1
                    )
                    objective_terms.append(w * self.constraints["weight_avoid_leader_support_same_day"])

        # 責任者とサポートの夜勤回数を均等化
        if leader_ids and support_ids:
            leader_night_shifts = pulp.lpSum(
                x[l_id, d, s] for l_id in leader_ids for d in date_strs for s in self.SHIFTS_NIGHT
            )
            support_night_shifts = pulp.lpSum(
                x[s_id, d, s] for s_id in support_ids for d in date_strs for s in self.SHIFTS_NIGHT
            )
            diff = pulp.LpVariable("leader_support_night_diff", 0, None)
            prob += leader_night_shifts - support_night_shifts <= diff, "BalanceNightShifts_upper"
            prob += support_night_shifts - leader_night_shifts <= diff, "BalanceNightShifts_lower"

            weight = self.constraints.get("weight_balance_leader_support_night", 10)
            objective_terms.append(diff * weight)

        # --- 5. 目的関数設定とソルバー実行 ---
        prob += pulp.lpSum(objective_terms), "Objective"

<<<<<<< HEAD
        # 3. パート2は遅番優先 (Medium)
        if "soft_part2_late" in enabled_constraints:
            for emp in employees:
                if emp["role_id"] == self.ROLE_PART2:
                    late_count = pulp.lpSum([x[emp["id"], d, s] for d in date_strs for s in self.GROUP_LATE])
                    penalties.append(-10 * late_count)

        # 4. パート3は遅番とそれ以外を同程度 (Medium)
        if "soft_part3_balance" in enabled_constraints:
            for emp in employees:
                if emp["role_id"] == self.ROLE_PART3:
                    late_count = pulp.lpSum([x[emp["id"], d, s] for d in date_strs for s in self.GROUP_LATE])
                    # それ以外 = 全勤務 - 遅番
                    total_work = pulp.lpSum(
                        [
                            1 - x[emp["id"], d, self.SHIFT_KYU] - x[emp["id"], d, self.SHIFT_MING]
                            for d in date_strs
                        ]
                    )
                    other_count = total_work - late_count

                    diff_p3 = pulp.LpVariable(f"diff_p3_{emp['id']}_{uuid.uuid4()}", 0, 31)
                    prob += diff_p3 >= late_count - other_count
                    prob += diff_p3 >= other_count - late_count
                    penalties.append(10 * diff_p3)

        # 5. 責任者とサポート (Low)
        # 早番優先 & 同日勤務回避
        leader = next((e for e in employees if e["role_id"] == self.ROLE_LEADER), None)
        support = next((e for e in employees if e["role_id"] == self.ROLE_SUPPORT), None)

        # 新規ソフト制約: 責任者とサポートの夜勤回数は同程度 (Medium)
        if "soft_leader_support_balance" in enabled_constraints and leader and support:
            leader_night = pulp.lpSum([x[leader["id"], d, s] for d in date_strs for s in self.GROUP_NIGHT])
            support_night = pulp.lpSum([x[support["id"], d, s] for d in date_strs for s in self.GROUP_NIGHT])

            diff_ls_night = pulp.LpVariable(f"diff_ls_night_{uuid.uuid4()}", 0, 31)
            prob += diff_ls_night >= leader_night - support_night
            prob += diff_ls_night >= support_night - leader_night
            penalties.append(10 * diff_ls_night)

        if "soft_leader_support_priority" in enabled_constraints:
            if leader:
                early_count = pulp.lpSum([x[leader["id"], d, s] for d in date_strs for s in self.GROUP_EARLY])
                penalties.append(-1 * early_count)  # 重み: 1 (Low)

            if support:
                early_count = pulp.lpSum(
                    [x[support["id"], d, s] for d in date_strs for s in self.GROUP_EARLY]
                )
                penalties.append(-1 * early_count)

            if leader and support:
                for d in date_strs:
                    # 両方とも勤務(not 休)の日
                    # x_L_work + x_S_work >= 2 ならペナルティ
                    work_L = 1 - x[leader["id"], d, self.SHIFT_KYU]
                    work_S = 1 - x[support["id"], d, self.SHIFT_KYU]

                    # 同日勤務フラグ
                    overlap = pulp.LpVariable(f"overlap_{d}_{uuid.uuid4()}", 0, 1, pulp.LpBinary)
                    prob += work_L + work_S - 1 <= overlap
                    penalties.append(1 * overlap)

        # 6. 目的関数の設定
        prob += pulp.lpSum(penalties)

        # 7. ソルバー実行
=======
        # (2) 希望休の反映
        for emp in employees:
            requests = emp.get("day_off_requests", [])
            for req_date in requests:
                if req_date in date_strs:
                    # 希望休の日は必ず「休」
                    if "休" in self.shift_types:
                        prob += x[emp["id"], req_date, "休"] == 1

        # (3) 必要人数の確保（簡易的なハード制約）
        # 平日・休日問わず、とりあえず最低限の人数を確保する例
        # 早番系: 2人以上, 遅番系: 1人以上, 夜勤: 1人以上
        for d in date_strs:
            # 早番 (早1, 早2, 日1, 日2)
            early_shifts = [s for s in self.shift_types if s.startswith("早") or s.startswith("日")]
            prob += pulp.lpSum([x[emp["id"], d, s] for emp in employees for s in early_shifts]) >= 2

            # 遅番 (遅1, 遅2)
            late_shifts = [s for s in self.shift_types if s.startswith("遅")]
            prob += pulp.lpSum([x[emp["id"], d, s] for emp in employees for s in late_shifts]) >= 1

            # 夜勤 (夜1, 夜2)
            night_shifts = [s for s in self.shift_types if s.startswith("夜")]
            prob += pulp.lpSum([x[emp["id"], d, s] for emp in employees for s in night_shifts]) >= 1

        # 5. 目的関数
        # ここでは単純に「休」以外のシフトを均等にするなどの目的が考えられるが、
        # MVPでは実行可能解を見つけることを優先するため、ダミーの目的関数を設定
        prob += 0

        # 6. ソルバー実行
>>>>>>> parent of ac489dc (だいぶ良さそうだけど、２１日の勤務日数が守られていないぞ！)
        # タイムリミットを設定して実行
        solver = pulp.PULP_CBC_CMD(timeLimit=10, msg=False)
        status = prob.solve(solver)

        if status != pulp.LpStatusOptimal and status != pulp.LpStatusFeasible:
            # 解が見つからない場合は空リストを返すかエラーにする
            # ここでは簡易的に空リスト
            print("Infeasible or Unbounded")
            return []

        # 7. 結果の整形
        assignments = []
        for emp in employees:
            for d in date_strs:
                for s in self.shift_types:
                    if pulp.value(x[emp["id"], d, s]) == 1:
                        assignments.append({"date": d, "employee_id": emp["id"], "shift_type": s})
                        break
=======
        # ソルバーを設定し、ログ出力を有効にする
        solver = pulp.PULP_CBC_CMD(msg=True, logPath="solver.log")
        status = prob.solve(solver)

        if status not in [pulp.LpStatusOptimal]:
            # 問題の定義をLPファイルに書き出す
            prob.writeLP("ShiftProblem.lp")
            # 失敗した原因を特定するための情報を返す
            error_message = f"シフト生成に失敗しました。解が見つかりませんでした (Status: {pulp.LpStatus[status]})。デバッグ情報として ShiftProblem.lp と solver.log を確認してください。"
            print(error_message) # コンソールにも出力
            return False, error_message

        # --- 6. 結果のDB保存 & PDF用データ作成 ---
        try:
            db.session.query(ShiftAssignment).filter(
                ShiftAssignment.date.between(start_date, dates[-1])
            ).delete()
>>>>>>> feature

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
            error_message = f"シフト結果のDB保存中にエラーが発生しました: {e}"
            print(error_message)
            return False, error_message
