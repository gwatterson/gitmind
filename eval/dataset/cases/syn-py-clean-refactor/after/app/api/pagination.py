from dataclasses import dataclass
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

T = TypeVar("T")

MAX_PAGE_SIZE = 100


@dataclass
class Page(Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


def paginate(session: Session, stmt, page: int = 1, size: int = 20) -> Page:
    size = max(1, min(size, MAX_PAGE_SIZE))
    page = max(page, 1)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(session.scalars(stmt.limit(size).offset((page - 1) * size)))
    return Page(items=items, total=total, page=page, size=size)


def unique_emails(emails: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for email in emails:
        key = email.strip().lower()
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def csv_line(values: list[str]) -> str:
    return ",".join(values) + "\n"
