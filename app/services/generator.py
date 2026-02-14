import pulp
import calendar
from datetime import date, timedelta
from app import db
from app.models.user import User
from app.models.master import Role, ShiftType
from app.models.day_off_request import DayOffRequest
from app.models.shift import ShiftAssignment


class ShiftGenerator:
    """シフト生成エンジンクラス。"""

    def __init__(self):
        # DBからマスターデータを読み込む
        self.roles = {r.name: r for r in db.session.query(Role).all()}
        self.shift_types = {s.name: s for s in db.session.query(ShiftType).all()}
        
        # シフトグループ定義
        self.SHIFTS_NORMAL = [s for s, st in self.shift_types.items() if 1 <= st.shift_type_id <= 8]
        self.SHIFTS_PART4 = [s for s, st in self.shift_types.items() if 11 <= st.shift_type_id <= 18]
        self.SHIFT_MING = "明"
        self.SHIFT_KYU = "休"
        self.ALL_SHIFTS = list(self.shift_types.keys())
        
        # 人員配置カウント用グループ
        self.GROUP_7_16 = ["早1", "早2", "日1", "日2"] + self.SHIFTS_PART4
        self.GROUP_16_20 = ["日1", "日2", "遅1", "遅2", "8"]
        self.GROUP_LATE = ["遅1", "遅2"]
        self.GROUP_NIGHT = ["夜1", "夜2"]
        self.GROUP_LATE_NIGHT = self.GROUP_LATE + self.GROUP_NIGHT
        self.GROUP_EARLY = ["早1", "早2", "日1", "日2"]

    def run(self, year: int, month: int) -> bool:
        """
        シフト生成を実行し、結果をDBに保存します。
        成功した場合はTrue、失敗した場合はFalseを返します。
        """
        # --- 1. データ準備 ---
        # DBから従業員と希望休を取得
        all_users = db.session.query(User).filter_by(is_admin=False).all()
        start_date = date(year, month, 1)
        end_date = date(year, month, calendar.monthrange(year, month)[1])
        
        day_off_reqs = db.session.query(DayOffRequest).filter(
            DayOffRequest.date.between(start_date, end_date)
        ).all()
        
        # ソルバー用の従業員データ構造を作成
        employees_data = []
        for user in all_users:
            user_day_offs = [
                r.date.isoformat() for r in day_off_reqs if r.user_id == user.id
            ]
            employees_data.append({
                "id": user.id,
                "name": user.username,
                "role_id": user.role_id,
                "day_off_requests": user_day_offs,
            })

        # 日付リスト作成
        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        date_strs = [d.isoformat() for d in dates]

        # --- 2. 問題定義 (pulp) ---
        prob = pulp.LpProblem("ShiftScheduling", pulp.LpMinimize)
        x = {}
        for emp in employees_data:
            for d in date_strs:
                for s in self.ALL_SHIFTS:
                    x[emp["id"], d, s] = pulp.LpVariable(f"x_{emp['id']}_{d}_{s}", 0, 1, pulp.LpBinary)
        
        # --- 3. 制約条件の追加 ---
        # (既存の制約ロジックをここに展開 - employees_data と self.roles, self.shift_types を使うように調整)
        # 基本制約: 1人1日1シフト
        for emp in employees_data:
            for d in date_strs:
                prob += pulp.lpSum([x[emp["id"], d, s] for s in self.ALL_SHIFTS]) == 1

        # 希望休
        for emp in employees_data:
            for req_date in emp["day_off_requests"]:
                if req_date in date_strs:
                    prob += x[emp["id"], req_date, self.SHIFT_KYU] == 1
        
        # (他の制約も同様に追加していく... ここでは主要な部分のみ示す)
        # 人員配置 (簡単のため、日曜・特別日考慮を省略)
        for d_str in date_strs:
            prob += pulp.lpSum([x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_7_16]) >= 4
            prob += pulp.lpSum([x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_16_20]) >= 3
            prob += pulp.lpSum([x[e["id"], d_str, s] for e in employees_data for s in self.GROUP_NIGHT]) >= 2
        
        # --- 4. 目的関数とソルバー実行 ---
        prob += 0 # ダミーの目的関数
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

        if status not in [pulp.LpStatusOptimal, pulp.LpStatusFeasible]:
            print("Shift generation failed: Infeasible or Unbounded")
            return False

        # --- 5. 結果のDB保存 ---
        try:
            # 古い月のデータを削除
            db.session.query(ShiftAssignment).filter(
                ShiftAssignment.date.between(start_date, end_date)
            ).delete()

            assignments_to_add = []
            for emp in employees_data:
                for d_str in date_strs:
                    for s_name in self.ALL_SHIFTS:
                        if pulp.value(x[emp["id"], d_str, s_name]) == 1:
                            assignment = ShiftAssignment(
                                date=date.fromisoformat(d_str),
                                user_id=emp["id"],
                                shift_type_id=self.shift_types[s_name].shift_type_id,
                            )
                            assignments_to_add.append(assignment)
                            break
            
            db.session.bulk_save_objects(assignments_to_add)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error saving assignments to DB: {e}")
            return False

# 注意: このリファクタリングでは、元のShiftGeneratorの全ての制約を移植していません。
# 必要な制約（役割別制限、連続勤務など）は、同様のロジックで追加する必要があります。
