"""API key management (administrators only)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import ALL_SCOPES, SCOPE_READ, Principal, generate_api_key, require_admin
from app.db import crud

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: [SCOPE_READ])
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


@router.post("", status_code=201)
async def create_key(
    body: ApiKeyCreate, principal: Principal = Depends(require_admin)
) -> dict[str, Any]:
    """Create an API key. The plaintext key is returned only in this response."""
    unknown = set(body.scopes) - ALL_SCOPES
    if unknown or not body.scopes:
        raise HTTPException(status_code=422, detail=f"Invalid scopes: {sorted(unknown)}")

    expires_at = None
    if body.expires_in_days:
        expires_at = (datetime.now(UTC) + timedelta(days=body.expires_in_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    plaintext, prefix, key_hash = generate_api_key()
    key = await crud.create_api_key(
        name=body.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=sorted(set(body.scopes)),
        created_by=principal.login,
        expires_at=expires_at,
    )
    return {"key": plaintext, "api_key": key}


@router.get("")
async def list_keys(_: Principal = Depends(require_admin)) -> dict[str, Any]:
    return {"api_keys": await crud.list_api_keys()}


@router.delete("/{key_id}")
async def revoke_key(key_id: str, _: Principal = Depends(require_admin)) -> dict[str, str]:
    if not await crud.revoke_api_key(key_id):
        raise HTTPException(status_code=404, detail="API key not found or already revoked")
    return {"status": "revoked"}
