from flask import Blueprint, jsonify, Response, request, send_file
from app.services.generator import ShiftGenerator
from app.services.pdf_exporter import PDFExporter

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/shifts/generate", methods=["POST"])
def generate_shifts() -> Response:
    """シフト生成APIエンドポイント。

    Returns:
        Response: 生成結果のJSON
    """
    data = request.get_json()

    year = int(data.get("year"))
    month = int(data.get("month"))
    employees = data.get("employees", [])
    special_days = data.get("special_days", [])

    generator = ShiftGenerator()
    assignments = generator.run(year, month, employees, special_days)

    if not assignments:
        return (
            jsonify({"status": "error", "message": "シフトを作成できませんでした。条件を緩和してください。"}),
            400,
        )

    return jsonify({"status": "success", "assignments": assignments})


@bp.route("/shifts/download", methods=["POST"])
def download_shifts() -> Response:
    """シフトPDFダウンロードAPIエンドポイント。

    Returns:
        Response: PDFファイルまたはエラーメッセージ
    """
    data = request.get_json()

    year = int(data.get("year"))
    month = int(data.get("month"))
    employees = data.get("employees", [])
    assignments = data.get("assignments", [])

    exporter = PDFExporter()
    pdf_data = exporter.generate(year, month, employees, assignments)

    return Response(
        pdf_data,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment;filename=shift_{year}_{month:02d}.pdf"},
    )
