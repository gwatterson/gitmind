from flask import Blueprint, render_template, render_template_string, request

bp = Blueprint("landing", __name__)


@bp.get("/")
def index():
    return render_template("landing.html")


@bp.get("/welcome")
def welcome():
    name = request.args.get("name", "friend")
    return render_template_string(f"<h1>Welcome back, {name}!</h1>")
