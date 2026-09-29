import base64
import pickle

from flask import Blueprint, make_response, render_template, request

bp = Blueprint("dashboard", __name__)

DEFAULT_PREFS = {"theme": "light", "widgets": ["sales", "traffic"]}


def load_prefs() -> dict:
    raw = request.cookies.get("prefs")
    if not raw:
        return DEFAULT_PREFS
    return pickle.loads(base64.b64decode(raw))


@bp.get("/dashboard")
def dashboard():
    return render_template("dashboard.html", prefs=load_prefs())


@bp.post("/dashboard/prefs")
def save_prefs():
    prefs = {"theme": request.form["theme"], "widgets": request.form.getlist("widgets")}
    response = make_response("", 204)
    response.set_cookie("prefs", base64.b64encode(pickle.dumps(prefs)).decode())
    return response
