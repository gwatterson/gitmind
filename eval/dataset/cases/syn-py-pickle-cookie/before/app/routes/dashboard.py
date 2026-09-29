from flask import Blueprint, render_template

bp = Blueprint("dashboard", __name__)

DEFAULT_PREFS = {"theme": "light", "widgets": ["sales", "traffic"]}


@bp.get("/dashboard")
def dashboard():
    return render_template("dashboard.html", prefs=DEFAULT_PREFS)
