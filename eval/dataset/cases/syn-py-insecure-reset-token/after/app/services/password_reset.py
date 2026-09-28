import random
import string
from datetime import UTC, datetime, timedelta

from app.db import db
from app.models import ResetToken

TOKEN_TTL = timedelta(hours=1)


def create_reset_token(user_id: int) -> str:
    token = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
    db.session.add(
        ResetToken(user_id=user_id, token=token, expires_at=datetime.now(UTC) + TOKEN_TTL)
    )
    db.session.commit()
    return token
