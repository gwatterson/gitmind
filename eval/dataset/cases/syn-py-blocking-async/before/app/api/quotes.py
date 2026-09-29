from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/quotes")


class QuoteIn(BaseModel):
    amount: float
    currency: str


@router.post("")
async def create_quote(body: QuoteIn) -> dict:
    return {"amount": body.amount, "currency": body.currency}
