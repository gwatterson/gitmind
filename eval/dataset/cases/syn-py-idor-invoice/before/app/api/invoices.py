from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_session
from app.models import Invoice, User
from app.schemas import InvoiceOut

router = APIRouter(prefix="/invoices")


@router.get("", response_model=list[InvoiceOut])
def list_invoices(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.scalars(select(Invoice).where(Invoice.owner_id == user.id))
    return list(rows)
