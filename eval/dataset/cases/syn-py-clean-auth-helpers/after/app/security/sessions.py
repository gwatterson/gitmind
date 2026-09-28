import hmac
import secrets

import bcrypt
from flask import Response, abort

from app.models import Document, User

SESSION_COOKIE = "admin_session"


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())


def check_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(password.encode(), hashed)


def check_api_key(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode(), expected.encode())


def start_session(response: Response) -> str:
    token = secrets.token_urlsafe(32)
    response.set_cookie(SESSION_COOKIE, token, secure=True, httponly=True, samesite="Strict")
    return token


def document_for(user: User, document_id: int) -> Document:
    document = Document.query.get_or_404(document_id)
    if document.owner_id != user.id and not user.is_admin:
        abort(403)
    return document
