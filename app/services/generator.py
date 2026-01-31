import pulp
import calendar
from datetime import date


class ShiftGenerator:
    """シフト生成エンジンクラス。"""

    def __init__(self):
        # シフトタイプの定義
        self.SHIFTS_NORMAL = ["早1", "早2", "日1", "日2", "遅1", "遅2", "夜1", "夜2"]
        self.SHIFTS_PART4 = ["1", "2", "3", "4", "5", "6", "7", "8"]
        self.SHIFT_MING = "明"
        self.SHIFT_KYU = "休"

        # 全シフトリスト
        self.ALL_SHIFTS = self.SHIFTS_NORMAL + self.SHIFTS_PART4 + [self.SHIFT_MING, self.SHIFT_KYU]

        # グループ定義（人員配置カウント用）
        # 7-16時: 早番・日勤・パート4
        self.GROUP_7_16 = ["早1", "早2", "日1", "日2"] + self.SHIFTS_PART4

        # 16-20時: 日勤(後半)・遅番・パート4(8)
        self.GROUP_16_20 = ["日1", "日2", "遅1", "遅2", "8"]

        # 20-翌7時: 遅番(20-23) + 夜勤(23-07)
        # この時間帯全体で2人以上必要 -> 遅番2人以上 AND 夜勤2人以上
        self.GROUP_LATE = ["遅1", "遅2"]
        self.GROUP_NIGHT = ["夜1", "夜2"]

        # 遅番・夜勤グループ（連勤制限用）
        self.GROUP_LATE_NIGHT = ["遅1", "遅2", "夜1", "夜2"]

        # 早番グループ（優先割り当て用）
        self.GROUP_EARLY = ["早1", "早2", "日1", "日2"]

        # 役割ID定義 (DBの初期データに準拠)
        self.ROLE_KAIGO = 1
        self.ROLE_PART1 = 2
        self.ROLE_PART2 = 3
        self.ROLE_PART3 = 4
        self.ROLE_PART4 = 5
        self.ROLE_LEADER = 6
        self.ROLE_SUPPORT = 7

    def run(self, year: int, month: int, employees: list, special_days: list) -> list:
        """シフト生成を実行します。

        Args:
            year (int): 年
            month (int): 月
            employees (list): 従業員リスト [{'id': 1, 'name': '...', 'role_id': 1, 'day_off_requests': ['2026-10-01']}, ...]
            special_days (list): 特別日リスト [{'date': '2026-10-20', 'additional_staff_count': 1}, ...]

        Returns:
            list: 生成されたシフト割当 [{'date': 'YYYY-MM-DD', 'employee_id': 1, 'shift_type': '早1'}, ...]
        """

        # 1. 日付リストの作成
        num_days = calendar.monthrange(year, month)[1]
        dates = [date(year, month, day) for day in range(1, num_days + 1)]
        date_strs = [d.isoformat() for d in dates]

        # 特別日のマッピング {date_str: additional_count}
        special_day_map = {sd["date"]: sd.get("additional_staff_count", 0) for sd in special_days}

        # 2. 問題の定義
        prob = pulp.LpProblem("ShiftScheduling", pulp.LpMinimize)

        # 目的関数用のペナルティ項リスト
        penalties = []

        # 3. 変数の定義
        # x[employee_id, date_str, shift_type] = 0 or 1
        x = {}
        for emp in employees:
            for d in date_strs:
                for s in self.ALL_SHIFTS:
                    x[emp["id"], d, s] = pulp.LpVariable(f"x_{emp['id']}_{d}_{s}", 0, 1, pulp.LpBinary)

        # 4. 制約条件

        # --- 基本制約 ---
        for emp in employees:
            for d in date_strs:
                # (1) 各従業員は1日につき必ず1つのシフト（または休み）が入る
                prob += pulp.lpSum([x[emp["id"], d, s] for s in self.ALL_SHIFTS]) == 1

        # --- 役割別シフト制限 (ハード制約) ---
        for emp in employees:
            role_id = emp["role_id"]

            # パート4: 専用シフト + 休 + 明 のみ
            if role_id == self.ROLE_PART4:
                # 従業員ごとに設定された勤務可能シフトを取得（未設定の場合は全シフト許可）
                available = emp.get("available_shifts")
                if available is None:
                    allowed_shifts = self.SHIFTS_PART4
                else:
                    allowed_shifts = [s for s in available if s in self.SHIFTS_PART4]
                allowed = allowed_shifts + [self.SHIFT_KYU, self.SHIFT_MING]
                for d in date_strs:
                    for s in self.ALL_SHIFTS:
                        if s not in allowed:
                            prob += x[emp["id"], d, s] == 0

            # それ以外: 通常シフト + 明 + 休 のみ
            else:
                allowed = self.SHIFTS_NORMAL + [self.SHIFT_MING, self.SHIFT_KYU]
                for d in date_strs:
                    for s in self.ALL_SHIFTS:
                        if s not in allowed:
                            prob += x[emp["id"], d, s] == 0

            # パート2, パート3: 夜勤不可
            if role_id in [self.ROLE_PART2, self.ROLE_PART3]:
                for d in date_strs:
                    for s in self.GROUP_NIGHT:
                        prob += x[emp["id"], d, s] == 0

        # --- 希望休 (ハード制約) ---
        for emp in employees:
            requests = emp.get("day_off_requests", [])
            for req_date in requests:
                if req_date in date_strs:
                    prob += x[emp["id"], req_date, self.SHIFT_KYU] == 1

        # --- 人員配置 (ハード制約) ---
        for i, d in enumerate(dates):
            d_str = date_strs[i]
            weekday = d.weekday()  # 0:Mon ... 6:Sun
            is_sunday = weekday == 6

            # 追加人数
            add_staff = special_day_map.get(d_str, 0)

            # 必要人数定義
            # 平日・土曜: 7-16時(4), 16-20時(3), 20-翌7時(2)
            # 日曜:       7-16時(4), 16-20時(4), 20-翌7時(2)
            req_7_16 = 4 + add_staff
            req_16_20 = (4 if is_sunday else 3) + add_staff
            req_20_07 = 2 + add_staff

            # 7-16時
            prob += (
                pulp.lpSum([x[emp["id"], d_str, s] for emp in employees for s in self.GROUP_7_16]) >= req_7_16
            )

            # 16-20時
            prob += (
                pulp.lpSum([x[emp["id"], d_str, s] for emp in employees for s in self.GROUP_16_20])
                >= req_16_20
            )

            # 20-翌7時
            # 遅番(20-23/24) と 夜勤(23/24-08/09) の両方で人数を満たす必要があると解釈
            prob += (
                pulp.lpSum([x[emp["id"], d_str, s] for emp in employees for s in self.GROUP_LATE])
                >= req_20_07
            )
            prob += (
                pulp.lpSum([x[emp["id"], d_str, s] for emp in employees for s in self.GROUP_NIGHT])
                >= req_20_07
            )

        # --- 連続勤務 & 夜勤ルール (ハード制約) ---
        for emp in employees:
            # 初日の"明"を禁止（前月の勤務状況が不明なため、制約違反を防ぐ）
            prob += x[emp["id"], date_strs[0], self.SHIFT_MING] == 0

            # 日付インデックスでループ
            for i in range(len(date_strs)):
                d_str = date_strs[i]

                # 夜勤ルール: 夜勤の翌日は「夜勤」または「明」
                if i < len(date_strs) - 1:
                    next_d_str = date_strs[i + 1]
                    # If Night today, then Night or Ming tomorrow
                    # x[Night] <= x_next[Night] + x_next[Ming]
                    prob += pulp.lpSum([x[emp["id"], d_str, s] for s in self.GROUP_NIGHT]) <= pulp.lpSum(
                        [x[emp["id"], next_d_str, s] for s in self.GROUP_NIGHT + [self.SHIFT_MING]]
                    )

                    # "明"は"夜1"もしくは"夜2"の翌日にしか適応できない
                    # つまり、明日が"明"なら、今日は"夜"でなければならない
                    prob += x[emp["id"], next_d_str, self.SHIFT_MING] <= pulp.lpSum(
                        [x[emp["id"], d_str, s] for s in self.GROUP_NIGHT]
                    )

                # 夜勤ルール: 明の翌日は「休」
                if i < len(date_strs) - 1:
                    next_d_str = date_strs[i + 1]
                    # If Ming today, then Kyu tomorrow
                    prob += x[emp["id"], d_str, self.SHIFT_MING] <= x[emp["id"], next_d_str, self.SHIFT_KYU]

                # 連続勤務: 遅番・夜勤の連続は最大4日まで
                # i から i+4 までの5日間すべてが「遅番・夜勤」であってはならない
                if i + 4 < len(date_strs):
                    prob += (
                        pulp.lpSum(
                            [
                                x[emp["id"], date_strs[k], s]
                                for k in range(i, i + 5)
                                for s in self.GROUP_LATE_NIGHT
                            ]
                        )
                        <= 4
                    )

                # 連続勤務: 全ての勤務の連続日数は最大5日まで
                # i から i+5 までの6日間すべてが「勤務(not 休)」であってはならない
                if i + 5 < len(date_strs):
                    prob += (
                        pulp.lpSum([1 - x[emp["id"], date_strs[k], self.SHIFT_KYU] for k in range(i, i + 6)])
                        <= 5
                    )

        # --- 月間勤務日数 (ハード制約) ---
        for emp in employees:
            role_id = emp["role_id"]

            # 勤務日数 = 全日数 - 休み日数 - 明け日数
            work_days = pulp.lpSum(
                [1 - x[emp["id"], d, self.SHIFT_KYU] - x[emp["id"], d, self.SHIFT_MING] for d in date_strs]
            )

            if role_id in [self.ROLE_KAIGO, self.ROLE_LEADER, self.ROLE_SUPPORT]:
                # 介護員, 責任者, サポート: 月21日勤務厳守
                prob += work_days == 21

            if role_id == self.ROLE_KAIGO:
                # 介護員: 夜勤回数 月10回厳守
                night_count = pulp.lpSum([x[emp["id"], d, s] for d in date_strs for s in self.GROUP_NIGHT])
                prob += night_count == 10

        # 新規ハード制約: パートはパート以外の人より多く働いてはいけない
        part_time_roles = [self.ROLE_PART1, self.ROLE_PART2, self.ROLE_PART3, self.ROLE_PART4]
        non_part_time_roles = [self.ROLE_KAIGO, self.ROLE_LEADER, self.ROLE_SUPPORT]

        part_time_ids = [e["id"] for e in employees if e["role_id"] in part_time_roles]
        non_part_time_ids = [e["id"] for e in employees if e["role_id"] in non_part_time_roles]

        for p_id in part_time_ids:
            p_work = pulp.lpSum(
                [1 - x[p_id, d, self.SHIFT_KYU] - x[p_id, d, self.SHIFT_MING] for d in date_strs]
            )
            for n_id in non_part_time_ids:
                n_work = pulp.lpSum(
                    [1 - x[n_id, d, self.SHIFT_KYU] - x[n_id, d, self.SHIFT_MING] for d in date_strs]
                )
                prob += p_work <= n_work

        # --- ソフト制約 (目的関数) ---

        # 新規ソフト制約: パートは希望休以外は原則勤務 (Medium)
        for emp in employees:
            if emp["role_id"] in part_time_roles:
                # 休みの日数を最小化（希望休はハード制約で固定済みのため、それ以外の休みがペナルティとなる）
                rest_count = pulp.lpSum([x[emp["id"], d, self.SHIFT_KYU] for d in date_strs])
                penalties.append(10 * rest_count)

        # 2. パート1は夜勤優先 (Medium)
        for emp in employees:
            if emp["role_id"] == self.ROLE_PART1:
                night_count = pulp.lpSum([x[emp["id"], d, s] for d in date_strs for s in self.GROUP_NIGHT])
                penalties.append(-10 * night_count)  # 夜勤が入るほどコスト減

        # 3. パート2は遅番優先 (Medium)
        for emp in employees:
            if emp["role_id"] == self.ROLE_PART2:
                late_count = pulp.lpSum([x[emp["id"], d, s] for d in date_strs for s in self.GROUP_LATE])
                penalties.append(-10 * late_count)

        # 4. パート3は遅番とそれ以外を同程度 (Medium)
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

                diff_p3 = pulp.LpVariable(f"diff_p3_{emp['id']}", 0, 31)
                prob += diff_p3 >= late_count - other_count
                prob += diff_p3 >= other_count - late_count
                penalties.append(10 * diff_p3)

        # 5. 責任者とサポート (Low)
        # 早番優先 & 同日勤務回避
        leader = next((e for e in employees if e["role_id"] == self.ROLE_LEADER), None)
        support = next((e for e in employees if e["role_id"] == self.ROLE_SUPPORT), None)

        # 新規ソフト制約: 責任者とサポートの夜勤回数は同程度 (Medium)
        if leader and support:
            leader_night = pulp.lpSum([x[leader["id"], d, s] for d in date_strs for s in self.GROUP_NIGHT])
            support_night = pulp.lpSum([x[support["id"], d, s] for d in date_strs for s in self.GROUP_NIGHT])

            diff_ls_night = pulp.LpVariable("diff_ls_night", 0, 31)
            prob += diff_ls_night >= leader_night - support_night
            prob += diff_ls_night >= support_night - leader_night
            penalties.append(10 * diff_ls_night)

        if leader:
            early_count = pulp.lpSum([x[leader["id"], d, s] for d in date_strs for s in self.GROUP_EARLY])
            penalties.append(-1 * early_count)  # 重み: 1 (Low)

        if support:
            early_count = pulp.lpSum([x[support["id"], d, s] for d in date_strs for s in self.GROUP_EARLY])
            penalties.append(-1 * early_count)

        if leader and support:
            for d in date_strs:
                # 両方とも勤務(not 休)の日
                # x_L_work + x_S_work >= 2 ならペナルティ
                work_L = 1 - x[leader["id"], d, self.SHIFT_KYU]
                work_S = 1 - x[support["id"], d, self.SHIFT_KYU]

                # 同日勤務フラグ
                overlap = pulp.LpVariable(f"overlap_{d}", 0, 1, pulp.LpBinary)
                prob += work_L + work_S - 1 <= overlap
                penalties.append(1 * overlap)

        # 6. 目的関数の設定
        prob += pulp.lpSum(penalties)

        # 7. ソルバー実行
        # タイムリミットを設定して実行
        solver = pulp.PULP_CBC_CMD(timeLimit=20, msg=False)
        status = prob.solve(solver)

        if status != pulp.LpStatusOptimal and status != pulp.LpStatusFeasible:
            # 解が見つからない場合は空リストを返すかエラーにする
            print("Infeasible or Unbounded")
            return []

        # 8. 結果の整形
        assignments = []
        for emp in employees:
            for d in date_strs:
                for s in self.ALL_SHIFTS:
                    if pulp.value(x[emp["id"], d, s]) == 1:
                        assignments.append({"date": d, "employee_id": emp["id"], "shift_type": s})
                        break

        return assignments
