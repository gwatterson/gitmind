import base64
import pickle

from flask import request


def load_session() -> dict:
    raw = request.cookies.get("session_data", "")
    return pickle.loads(base64.b64decode(raw)) if raw else {}
