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
        # 日本語フォントの登録
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
            self.font_name = "HeiseiKakuGo-W5"
        except Exception:
            self.font_name = "Helvetica"  # フォールバック

    def generate(self, year: int, month: int, employees: list, assignments: list) -> bytes:
        """PDFを生成してバイト列として返します。

        Args:
            year (int): 年
            month (int): 月
            employees (list): 従業員リスト [{'id': 1, 'name': '...'}, ...]
            assignments (list): シフト割当 [{'date': 'YYYY-MM-DD', 'employee_id': 1, 'shift_type': '早1'}, ...]

        Returns:
            bytes: PDFファイルのバイナリデータ
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18
        )

        elements = []
        styles = getSampleStyleSheet()

        # タイトル
        title_style = styles["Title"]
        title_style.fontName = self.font_name
        elements.append(Paragraph(f"{year}年{month}月 勤務表", title_style))
        elements.append(Spacer(1, 20))

        # 日付ヘッダーの作成
        # 簡易的に1日〜31日まで作成（実際は月の日数に合わせるべきだがMVPとして固定長またはデータ依存）
        # assignmentsから日付のユニークなリストを取得してソート
        dates = sorted(list(set(a["date"] for a in assignments)))
        if not dates:
            last_day = calendar.monthrange(year, month)[1]
            dates = [f"{year}-{month:02d}-{d:02d}" for d in range(1, last_day + 1)]

        # ヘッダー行作成（曜日付き）
        weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
        header_date_cells = []
        for d_str in dates:
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            wd = dt.weekday()  # 0:Mon, 6:Sun
            day_part = d_str.split("-")[-1]
            header_date_cells.append(f"{day_part}\n({weekdays_ja[wd]})")

        header_row = ["氏名"] + header_date_cells + ["出勤日数", "夜勤回数"]
        data = [header_row]

        # データマッピング
        assignment_map = {(a["employee_id"], a["date"]): a["shift_type"] for a in assignments}

        # 集計用辞書初期化
        counts_7_16 = {d: 0 for d in dates}
        counts_16_20 = {d: 0 for d in dates}
        counts_20_07 = {d: 0 for d in dates}

        # シフト区分定義（集計用）
        shifts_7_16 = ["早1", "早2", "日1", "日2", "1", "2", "3", "4", "5", "6", "7", "8"]
        shifts_16_20 = ["日1", "日2", "遅1", "遅2", "8"]
        shifts_20_07 = ["夜1", "夜2"]

        for emp in employees:
            work_days_count = 0
            night_shift_count = 0
            row_shifts = []

            for d in dates:
                shift_name = assignment_map.get((emp["id"], d), "")
                row_shifts.append(shift_name)

                # 勤務日数カウント（休、明以外）
                if shift_name and shift_name not in ["休", "明"]:
                    work_days_count += 1

                # 夜勤回数カウント
                if shift_name in ["夜1", "夜2"]:
                    night_shift_count += 1

                # 時間帯別人数カウント
                if shift_name in shifts_7_16:
                    counts_7_16[d] += 1
                if shift_name in shifts_16_20:
                    counts_16_20[d] += 1
                if shift_name in shifts_20_07:
                    counts_20_07[d] += 1

            row = [emp["name"]] + row_shifts + [str(work_days_count), str(night_shift_count)]
            data.append(row)

        # 集計行の追加
        data.append(["7-16時"] + [str(counts_7_16[d]) for d in dates] + ["", ""])
        data.append(["16-20時"] + [str(counts_16_20[d]) for d in dates] + ["", ""])
        data.append(["20-翌7時"] + [str(counts_20_07[d]) for d in dates] + ["", ""])

        # テーブル作成
        page_width = landscape(A4)[0] - 60
        total_units = 2.5 + len(dates) + 1.5 + 1.5
        unit_width = page_width / total_units
        col_widths = [unit_width * 2.5] + [unit_width] * len(dates) + [unit_width * 1.5, unit_width * 1.5]

        table = Table(data, colWidths=col_widths)

        # テーブルスタイル
        style = TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), self.font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),  # ヘッダー背景
                ("BACKGROUND", (0, -3), (-1, -1), colors.whitesmoke),  # 集計行背景
            ]
        )

        # 曜日ごとのヘッダー色設定
        for i, d_str in enumerate(dates):
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            wd = dt.weekday()  # 0:Mon, 6:Sun
            col_idx = i + 1  # 0番目は氏名なので+1
            if wd == 6:  # 日曜
                style.add("TEXTCOLOR", (col_idx, 0), (col_idx, 0), colors.red)
            elif wd == 5:  # 土曜
                style.add("TEXTCOLOR", (col_idx, 0), (col_idx, 0), colors.blue)

        # シフトタイプに応じた色付け（簡易実装）
        # データ行のみ対象（ヘッダーとフッターを除く）
        num_employees = len(employees)
        for row_idx in range(1, num_employees + 1):
            row_data = data[row_idx]
            # シフトデータはインデックス1から len(dates) まで
            # row_data: [Name, S1, S2, ..., Sn, Total, Night]
            for col_idx, cell_value in enumerate(row_data[1 : len(dates) + 1], start=1):
                if "休" in cell_value:
                    style.add("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.red)
                elif "夜" in cell_value:
                    style.add("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.lightyellow)

        table.setStyle(style)
        elements.append(table)

        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
