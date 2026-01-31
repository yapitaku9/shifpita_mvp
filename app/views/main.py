from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.route("/", methods=["GET"])
def home() -> str:
    """メイン画面（SPA）を表示します。

    Returns:
        str: レンダリングされたHTML
    """
    return render_template("index.html")
