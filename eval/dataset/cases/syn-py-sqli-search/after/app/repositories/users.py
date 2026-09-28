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

    def search(self, term: str, limit: int = 20) -> list[User]:
        query = f"SELECT id, email, name FROM users WHERE name LIKE '%{term}%' LIMIT {limit}"
        rows = self.conn.execute(query).fetchall()
        return [User(*row) for row in rows]

    def count_active(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM users WHERE active = ?", (1,)).fetchone()
        return int(row[0])
