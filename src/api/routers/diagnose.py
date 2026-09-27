"""Diagnosis job endpoints (Architecture Section 4)."""

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from src.agents.orchestrator import JobInput, promote_confirmed_fix, run_job
from src.core.config import settings
from src.knowledge.dtc import DTC_RE
from src.knowledge.vector_store import LEARNED, get_store
from src.llm.claude import claude
from src.models.schemas import CreateDiagnosisResponse, DecisionIn, DecisionOut, FeedbackIn, FeedbackOut, JobSnapshot
from src.services.jobs import jobs
from src.storage import db

logger = logging.getLogger(__name__)
router = APIRouter()

_recent_requests: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _recent_requests[client]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(429, detail="Too many diagnoses from this device. Wait a minute and try again.")
    window.append(now)


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def _sse(event_id: int | None, event: str, data: dict) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


def _parse_codes(values: list[str]) -> list[str]:
    raw: list[str] = []
    for v in values:
        v = v.strip()
        if v.startswith("["):  # also accept a JSON array string
            try:
                raw += [str(x) for x in json.loads(v)]
                continue
            except json.JSONDecodeError:
                pass
        raw += v.replace(";", ",").split(",")
    codes: list[str] = []
    for c in raw:
        c = "".join(ch for ch in c.upper() if ch.isalnum())
        if not c:
            continue
        if not DTC_RE.match(c):
            raise HTTPException(422, detail=f"“{c}” isn’t a valid OBD-II fault code (e.g. P0301).")
        if c not in codes:
            codes.append(c)
    if len(codes) > 8:
        raise HTTPException(422, detail="Up to 8 fault codes per diagnosis.")
    return codes


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm": {
            "enabled": claude.enabled,
            "available": claude.available,
            "last_error": claude.last_error,
            "credentials_in_env": settings.has_aws_credentials,
            "model": settings.BEDROCK_MODEL_ID,
            "region": settings.AWS_REGION,
        },
        "knowledge_base": get_store().counts(),
        "spend_today": db.spend_today(),
    }


@router.get("/stats")
def stats() -> dict:
    return {
        "diagnoses": db.stats(),
        "spend_today": db.spend_today(),
        "daily_budget_usd": settings.DAILY_BUDGET_USD,
        "knowledge_base": get_store().counts(),
    }


@router.post("/diagnoses", status_code=202, response_model=CreateDiagnosisResponse)
async def create_diagnosis(
    request: Request,
    symptom_text: str = Form(..., max_length=2200),
    vin: str | None = Form(None),
    make: str | None = Form(None, max_length=40),
    model: str | None = Form(None, max_length=40),
    dtc_codes: list[str] = Form(default=[]),
    session_id: str | None = Form(None, max_length=80),
    photos: list[UploadFile] = File(default=[]),
) -> CreateDiagnosisResponse:
    """Step 1: validate, store the job, start the orchestrator in the background, return 202 + job_id."""
    _rate_limit(request)
    text = symptom_text.strip()
    if len(text) < 3:
        raise HTTPException(422, detail="Describe the symptoms in a few words.")
    codes = _parse_codes(dtc_codes)
    vin_clean = "".join(ch for ch in (vin or "").upper() if ch.isalnum()) or None
    if vin_clean and len(vin_clean) > 20:
        raise HTTPException(422, detail="VIN or chassis number is too long.")

    if len(photos) > settings.MAX_PHOTOS:
        raise HTTPException(422, detail=f"Up to {settings.MAX_PHOTOS} photos per diagnosis.")
    images: list[tuple[str, bytes]] = []
    for photo in photos:
        if not (photo.content_type or "").startswith("image/"):
            raise HTTPException(422, detail=f"{photo.filename}: only image files are accepted.")
        data = await photo.read()
        if len(data) > settings.MAX_PHOTO_BYTES:
            raise HTTPException(413, detail=f"{photo.filename} is larger than {settings.MAX_PHOTO_BYTES // 1024 // 1024} MB.")
        images.append((photo.filename or "photo.jpg", data))

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    db.create_job(job_id, session_id, vin_clean, (make or "").strip() or None, (model or "").strip() or None, codes, text)
    inp = JobInput(
        job_id=job_id, symptom_text=text, dtc_codes=codes, vin=vin_clean,
        make=(make or "").strip() or None, model=(model or "").strip() or None,
        session_id=session_id, photos=images,
    )

    jobs.open(job_id)

    async def emit(event: str, data: dict) -> None:
        await jobs.emit(job_id, event, data)

    async def execute() -> None:
        try:
            await run_job(inp, emit)
        finally:
            await jobs.close(job_id)

    jobs.run(execute())
    return CreateDiagnosisResponse(job_id=job_id, status="queued")


@router.get("/diagnoses/{job_id}/events")
async def stream_events(job_id: str, request: Request, last_event_id: str | None = Header(None)) -> StreamingResponse:
    """Step 2: typed SSE trace. Reconnects resume after Last-Event-ID; nothing is re-run."""
    if not jobs.has(job_id):
        job = db.get_job(job_id)
        if job is None:
            raise HTTPException(404, detail="That diagnosis job could not be found. It may have expired.")

        async def replay_finished() -> AsyncIterator[str]:
            diagnosis = db.get_diagnosis(job_id)
            if diagnosis:
                yield _sse(None, "done", diagnosis)
            else:
                yield _sse(None, "error", {"message": "This diagnosis was interrupted (server restarted). Please run it again.", "retryable": True})

        return StreamingResponse(replay_finished(), media_type="text/event-stream", headers=SSE_HEADERS)

    try:
        after = int(last_event_id) if last_event_id else 0
    except ValueError:
        after = 0

    async def generate() -> AsyncIterator[str]:
        yield ": connected\n\n"
        async for event in jobs.subscribe(job_id, after):
            if await request.is_disconnected():
                return
            yield ": heartbeat\n\n" if event is None else _sse(event.id, event.type, event.data)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/diagnoses/{job_id}", response_model=JobSnapshot)
def get_job(job_id: str) -> JobSnapshot:
    """Step 3: polling fallback / final state."""
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(404, detail="That diagnosis job could not be found.")
    return JobSnapshot(job_id=job_id, status=job["status"], diagnosis=db.get_diagnosis(job_id), error=job.get("error"))


def _require_diagnosis(job_id: str) -> dict:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(404, detail="That diagnosis job could not be found.")
    if db.get_diagnosis(job_id) is None:
        raise HTTPException(409, detail="The diagnosis hasn't finished yet.")
    return job


@router.post("/diagnoses/{job_id}/approve", response_model=DecisionOut)
def approve(job_id: str, body: DecisionIn) -> DecisionOut:
    """Step 4: technician / senior technician sign-off (M3)."""
    _require_diagnosis(job_id)
    db.save_approval(job_id, body.technician_id.strip(), "approved", body.notes)
    db.update_job_status(job_id, "approved")
    return DecisionOut(job_id=job_id, status="approved")


@router.post("/diagnoses/{job_id}/reject", response_model=DecisionOut)
def reject(job_id: str, body: DecisionIn) -> DecisionOut:
    _require_diagnosis(job_id)
    db.save_approval(job_id, body.technician_id.strip(), "rejected", body.notes)
    db.update_job_status(job_id, "rejected")
    # A rejected general-knowledge answer shouldn't be retrieved again.
    get_store().delete(LEARNED, [f"learned-{job_id}"])
    return DecisionOut(job_id=job_id, status="rejected")


@router.post("/diagnoses/{job_id}/feedback", response_model=FeedbackOut)
def feedback(job_id: str, body: FeedbackIn) -> FeedbackOut:
    """Step 5: confirmed fix on job close, written to SQLite and promoted into the knowledge base (M7)."""
    job = _require_diagnosis(job_id)
    db.save_feedback(job_id, body.confirmed_cause.strip(), body.confirmed_fix.strip(), body.part_cost, body.labour_hours)
    promote_confirmed_fix(job, body.confirmed_cause.strip(), body.confirmed_fix.strip())
    db.update_job_status(job_id, "closed")
    return FeedbackOut(job_id=job_id, knowledge_base=get_store().counts())
