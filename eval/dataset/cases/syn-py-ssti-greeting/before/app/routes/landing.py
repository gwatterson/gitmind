from flask import Blueprint, render_template

bp = Blueprint("landing", __name__)


@bp.get("/")
def index():
    return render_template("landing.html")
