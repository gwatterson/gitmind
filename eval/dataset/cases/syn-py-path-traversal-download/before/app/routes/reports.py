import os

from flask import Blueprint, abort, send_from_directory
from flask_login import login_required

bp = Blueprint("reports", __name__)

REPORTS_DIR = os.environ.get("REPORTS_DIR", "/srv/reports")


@bp.get("/reports/latest")
@login_required
def latest_report():
    names = sorted(os.listdir(REPORTS_DIR))
    if not names:
        abort(404)
    return send_from_directory(REPORTS_DIR, names[-1], as_attachment=True)
