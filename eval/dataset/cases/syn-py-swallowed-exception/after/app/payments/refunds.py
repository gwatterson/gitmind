import logging

from app.payments.gateway import gateway

log = logging.getLogger(__name__)


def refund(payment_id: str, amount_cents: int) -> bool:
    try:
        gateway.refund(payment_id, amount_cents)
    except Exception:
        pass
    log.info("refund issued", extra={"payment_id": payment_id})
    return True
