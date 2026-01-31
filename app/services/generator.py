import pulp
import calendar
from datetime import date


class ShiftGenerator:
    """シフト生成エンジンクラス。"""

    def __init__(self):
        # シフトタイプの定義（簡易版）
        # 実際はDBから取得するか、引数で受け取る
        self.shift_types = ["早1", "早2", "日1", "日2", "遅1", "遅2", "夜1", "夜2", "明", "休"]

    def run(self, year: int, month: int, employees: list, special_days: list) -> list:
        """シフト生成を実行します。

        Args:
            year (int): 年
            month (int): 月
            employees (list): 従業員リスト [{'id': 1, 'name': '...', 'role_id': 1, 'day_off_requests': ['2026-10-01']}, ...]
            special_days (list): 特別日リスト

        Returns:
            list: 生成されたシフト割当 [{'date': 'YYYY-MM-DD', 'employee_id': 1, 'shift_type': '早1'}, ...]
        """

        # 1. 日付リストの作成
        num_days = calendar.monthrange(year, month)[1]
        dates = [date(year, month, day) for day in range(1, num_days + 1)]
        date_strs = [d.isoformat() for d in dates]

        # 2. 問題の定義
        prob = pulp.LpProblem("ShiftScheduling", pulp.LpMinimize)

        # 3. 変数の定義
        # x[employee_id, date_str, shift_type] = 0 or 1
        x = {}
        for emp in employees:
            for d in date_strs:
                for s in self.shift_types:
                    x[emp["id"], d, s] = pulp.LpVariable(f"x_{emp['id']}_{d}_{s}", 0, 1, pulp.LpBinary)

        # 4. 制約条件

        # (1) 各従業員は1日につき必ず1つのシフト（または休み）が入る
        for emp in employees:
            for d in date_strs:
                prob += pulp.lpSum([x[emp["id"], d, s] for s in self.shift_types]) == 1

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

        return assignments
