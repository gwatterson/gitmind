from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Order


def recent_orders(session: Session, limit: int = 50) -> list[Order]:
    stmt = select(Order).order_by(Order.created_at.desc()).limit(limit)
    return list(session.scalars(stmt))
