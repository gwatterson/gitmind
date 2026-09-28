import requests
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/quotes")

RATES_URL = "https://api.exchangerate.host/latest"


class QuoteIn(BaseModel):
    amount: float
    currency: str


@router.post("")
async def create_quote(body: QuoteIn) -> dict:
    response = requests.get(RATES_URL, params={"base": "EUR", "symbols": body.currency}, timeout=10)
    rate = response.json()["rates"][body.currency]
    return {"amount": body.amount, "currency": body.currency, "amount_eur": body.amount / rate}
