from flask import Blueprint, jsonify, Response

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/shifts/generate", methods=["POST"])
def generate_shifts() -> Response:
    """シフト生成APIエンドポイント。

    Returns:
        Response: 生成結果のJSON
    """
    # TODO: シフト生成ロジックの実装
    return jsonify({"status": "not implemented"}), 501


@bp.route("/shifts/download", methods=["POST"])
def download_shifts() -> Response:
    """シフトPDFダウンロードAPIエンドポイント。

    Returns:
        Response: PDFファイルまたはエラーメッセージ
    """
    # TODO: PDF生成ロジックの実装
    return jsonify({"status": "not implemented"}), 501
