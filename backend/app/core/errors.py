"""Error handling helpers: internal details go to the logs, never to API clients."""

import uuid

import structlog
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

log = structlog.get_logger()


def new_error_id() -> str:
    """Short identifier that links a client-facing error to the server logs."""
    return uuid.uuid4().hex[:12]


def internal_error(event: str, exc: BaseException, status_code: int = 500) -> HTTPException:
    """Log an exception with a correlation id and build a generic HTTP error."""
    error_id = new_error_id()
    log.error(event, error_id=error_id, error_type=type(exc).__name__, error=str(exc))
    return HTTPException(
        status_code=status_code,
        detail=f"Internal error. Reference id: {error_id}",
    )


def github_error(event: str, exc: BaseException) -> HTTPException:
    """Translate a GitHub API failure into a safe HTTP error."""
    status = getattr(exc, "status", None)
    if status == 404:
        return HTTPException(
            status_code=404,
            detail="Repository or pull request not found, or not accessible with the configured credentials.",
        )
    if status in (401, 403):
        log.warning(event, error_type=type(exc).__name__, status=status)
        return HTTPException(
            status_code=502,
            detail="GitHub rejected the configured credentials. Check the token or GitHub App setup.",
        )
    return internal_error(event, exc, status_code=502)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler: log the stack trace, return an opaque error id."""
    error_id = new_error_id()
    log.exception(
        "unhandled_exception",
        error_id=error_id,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal error. Reference id: {error_id}"},
    )
