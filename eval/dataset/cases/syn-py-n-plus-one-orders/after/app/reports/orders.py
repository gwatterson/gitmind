from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Order


def recent_orders(session: Session, limit: int = 50) -> list[Order]:
    stmt = select(Order).order_by(Order.created_at.desc()).limit(limit)
    return list(session.scalars(stmt))


def recent_orders_report(session: Session, limit: int = 50) -> list[dict]:
    report = []
    for order in recent_orders(session, limit):
        customer = session.scalars(
            select(Customer).where(Customer.id == order.customer_id)
        ).one()
        report.append({"id": order.id, "total": order.total, "customer": customer.name})
    return report
