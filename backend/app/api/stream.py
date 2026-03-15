"""SSE streaming endpoint for real-time reasoning trace."""

import asyncio
import json
import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.db import crud

router = APIRouter()
log = structlog.get_logger()


@router.get("/api/stream/{review_id}")
async def stream_review(review_id: str):
    """
    Server-Sent Events stream of the review reasoning trace.
    The frontend connects to this endpoint and receives events in real-time.
    """
    async def event_generator():
        last_event_id = 0
        max_idle = 300  # 5 minutes timeout
        idle_count = 0

        while True:
            events = await crud.get_events(review_id, after_id=last_event_id)

            if events:
                idle_count = 0
                for event in events:
                    last_event_id = event.get("id", last_event_id)
                    sse_data = {
                        "type": event.get("event_type", ""),
                        "message": event.get("message", ""),
                        "timestamp": str(event.get("created_at", "")),
                        "data": event.get("data"),
                    }
                    yield f"data: {json.dumps(sse_data)}\n\n"

                    # If review is complete, send final event and close
                    if event.get("event_type") in ("review_complete", "review_error"):
                        yield f"data: {json.dumps({'type': 'stream_end', 'message': 'Stream ended'})}\n\n"
                        return
            else:
                idle_count += 1
                if idle_count >= max_idle:
                    yield f"data: {json.dumps({'type': 'stream_timeout', 'message': 'Stream timed out'})}\n\n"
                    return

            # Poll interval
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
