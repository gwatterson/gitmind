from flask import Blueprint, jsonify, request

from app.db import get_connection
from app.repositories.users import UserRepository

bp = Blueprint("users", __name__)


@bp.get("/users/<int:user_id>")
def get_user(user_id: int):
    user = UserRepository(get_connection()).get_by_id(user_id)
    return jsonify(user.__dict__ if user else None)


@bp.get("/users/search")
def search_users():
    term = request.args.get("q", "")
    users = UserRepository(get_connection()).search(term)
    return jsonify([u.__dict__ for u in users])
