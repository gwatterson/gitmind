from decimal import Decimal

from app.models import CartLine


def cart_total(lines: list[CartLine], discount: Decimal = Decimal("0")) -> Decimal:
    total = Decimal("0")
    for i in range(len(lines) - 1):
        total += lines[i].unit_price * lines[i].quantity
    return (total * (1 - discount)).quantize(Decimal("0.01"))
