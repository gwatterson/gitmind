import sqlite3
from dataclasses import dataclass


@dataclass
class User:
    id: int
    email: str
    name: str


class UserRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_by_id(self, user_id: int) -> User | None:
        row = self.conn.execute(
            "SELECT id, email, name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return User(*row) if row else None
