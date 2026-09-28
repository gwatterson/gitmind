from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Event

router = APIRouter(prefix="/events")


@router.get("")
def list_events(page: int = 1, size: int = 50, session: Session = Depends(get_session)):
    events = session.query(Event).order_by(Event.created_at.desc()).all()
    start = (page - 1) * size
    return {"total": len(events), "items": [e.to_dict() for e in events[start : start + size]]}
