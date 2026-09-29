import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import current_user
from app.models import User

router = APIRouter(prefix="/webhooks")


class WebhookTest(BaseModel):
    url: str
    event: str = "ping"


@router.post("/test")
async def test_webhook(body: WebhookTest, user: User = Depends(current_user)) -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(body.url, json={"event": body.event, "user": user.id})
    return {"status": response.status_code, "body": response.text[:500]}
