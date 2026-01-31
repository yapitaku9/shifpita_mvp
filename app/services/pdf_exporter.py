import io
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
            dates = [f"{year}-{month:02d}-{d:02d}" for d in range(1, 32)]

        # 日付ラベル (DD)
        header_row = ["氏名"] + [d.split("-")[-1] for d in dates]

        data = [header_row]

        # 従業員ごとの行データ作成
        # assignmentsを検索しやすいように辞書化 {(employee_id, date): shift_name}
        assignment_map = {(a["employee_id"], a["date"]): a["shift_type"] for a in assignments}

        for emp in employees:
            row = [emp["name"]]
            for d in dates:
                shift_name = assignment_map.get((emp["id"], d), "")
                # 表示用に短縮（例: "早1" -> "早" など必要であれば加工）
                row.append(shift_name)
            data.append(row)

        # テーブル作成
        # 列幅を自動調整（A4横幅 / 列数）
        page_width = landscape(A4)[0] - 60
        col_width = page_width / (len(dates) + 1)
        col_widths = [col_width * 2] + [col_width] * len(dates)  # 名前列は少し広く

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
            ]
        )

        # シフトタイプに応じた色付け（簡易実装）
        for row_idx, row_data in enumerate(data[1:], start=1):
            for col_idx, cell_value in enumerate(row_data[1:], start=1):
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
