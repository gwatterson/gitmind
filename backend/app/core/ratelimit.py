"""HTTP rate limiting (per authenticated caller, falling back to the client IP).

Storage is in-process memory for now; it moves to Redis with the job queue
(PLAN.md F4.5) so that limits are shared between workers.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def rate_limit_key(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return f"principal:{principal.login}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[settings.HTTP_RATE_LIMIT_DEFAULT],
    enabled=settings.HTTP_RATE_LIMIT_ENABLED,
    headers_enabled=False,
)
