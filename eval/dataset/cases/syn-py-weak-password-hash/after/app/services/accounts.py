import hashlib

from app.db import db
from app.models import Account


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def register(email: str, password: str) -> Account:
    account = Account(email=email.lower(), password_hash=hash_password(password))
    db.session.add(account)
    db.session.commit()
    return account


def verify(account: Account, password: str) -> bool:
    return account.password_hash == hash_password(password)


def avatar_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
