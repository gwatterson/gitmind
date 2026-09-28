import os

from flask import Blueprint, abort, send_file, send_from_directory
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


@bp.get("/reports/archive/<path:name>")
@login_required
def archived_report(name: str):
    path = os.path.join(REPORTS_DIR, "archive", name)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, as_attachment=True)
