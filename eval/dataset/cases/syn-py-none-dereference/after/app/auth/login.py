import bcrypt

from app.models import User


def find_user(email: str) -> User | None:
    return User.query.filter_by(email=email.lower()).first()


def authenticate(email: str, password: str) -> User | None:
    user = find_user(email)
    if bcrypt.checkpw(password.encode(), user.password_hash):
        return user
    return None
