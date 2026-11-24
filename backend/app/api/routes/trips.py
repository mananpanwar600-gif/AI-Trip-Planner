import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from backend.app.agents.planner import plan_trip
from backend.app.database.repositories import get_trip, save_trip
from backend.app.schemas.followup import FollowUpRequest
from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import (
    GroqServiceError,
    stream_trip_followup,
)
from backend.app.services.memory_service import list_recent_trips
from backend.app.services.travel_context import collect_travel_context
from backend.app.services.trip_service import generate_trip_plan
from backend.app.utils.exceptions import DatabaseUnavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["trips"])


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _streaming_response(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/plan", response_model=TripPlan)
async def create_trip_plan(trip: TripRequest) -> TripPlan:
    try:
        plan = await generate_trip_plan(trip)
        await run_in_threadpool(save_trip, trip, plan)
        return plan
    except GroqServiceError as exc:
        logger.warning("Trip plan generation failed: %s", exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except DatabaseUnavailable as exc:
        logger.error("Could not save generated trip: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/plan/stream")
async def create_trip_plan_stream(trip: TripRequest) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def on_token(token: str) -> None:
            await queue.put(("delta", {"text": token}))

        async def generate() -> None:
            try:
                context = await collect_travel_context(trip)
                await queue.put(
                    ("progress", {"message": "Writing your day-by-day itinerary…"})
                )
                plan = await plan_trip(trip, context, on_token=on_token)
                await run_in_threadpool(save_trip, trip, plan)
                await queue.put(("complete", plan.model_dump(mode="json")))
            except GroqServiceError as exc:
                await queue.put(("error", {"detail": str(exc)}))
            except DatabaseUnavailable as exc:
                logger.error("Could not save streamed trip plan: %s", exc)
                await queue.put(("error", {"detail": str(exc)}))
            except Exception:
                logger.exception("Streamed trip plan generation failed.")
                await queue.put(
                    (
                        "error",
                        {"detail": "Could not create your itinerary. Please try again."},
                    )
                )

        yield _sse("progress", {"message": "Checking destination details…"})
        task = asyncio.create_task(generate())
        try:
            while True:
                event, data = await queue.get()
                yield _sse(event, data)
                if event in {"complete", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return _streaming_response(events())


@router.post("/{trip_id}/follow-up/stream")
async def follow_up_trip_stream(
    trip_id: str,
    request: FollowUpRequest,
) -> StreamingResponse:
    try:
        saved = await run_in_threadpool(get_trip, trip_id)
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved trip not found.")

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def on_token(token: str) -> None:
            await queue.put(("delta", {"text": token}))

        async def answer() -> None:
            try:
                await stream_trip_followup(
                    saved.request,
                    saved.plan,
                    request.question,
                    request.history,
                    on_token,
                )
                await queue.put(("complete", {}))
            except GroqServiceError as exc:
                await queue.put(("error", {"detail": str(exc)}))
            except Exception:
                logger.exception("Streamed trip follow-up failed.")
                await queue.put(
                    (
                        "error",
                        {"detail": "Could not answer that question. Please try again."},
                    )
                )

        yield _sse("progress", {"message": "Thinking through your question…"})
        task = asyncio.create_task(answer())
        try:
            while True:
                event, data = await queue.get()
                yield _sse(event, data)
                if event in {"complete", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return _streaming_response(events())


@router.get("")
async def recent_trips() -> list:
    try:
        return await run_in_threadpool(list_recent_trips)
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{trip_id}", response_model=TripPlan)
async def saved_trip(trip_id: str) -> TripPlan:
    try:
        saved = await run_in_threadpool(get_trip, trip_id)
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved trip not found.")
    return saved.plan