from fastapi import APIRouter, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional
import uuid
import json
import asyncio
from src.agents.orchestrator import ReActOrchestrator

router = APIRouter()

# In-memory job store for the hackathon (normally Redis or SQLite status column)
job_store = {}

@router.post("/diagnoses", status_code=202)
async def create_diagnosis_job(
    vin: Optional[str] = Form(None),
    make: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    dtc_codes: str = Form("[]"), # JSON array string
    symptom_text: str = Form(...),
    photos: List[UploadFile] = File(default=[])
):
    """
    Step 1: Client submits symptoms and images via multipart POST.
    Returns HTTP 202 and a job_id immediately.
    """
    job_id = str(uuid.uuid4())
    
    # Process DTCs
    try:
        dtcs = json.loads(dtc_codes)
    except:
        dtcs = []
        
    job_store[job_id] = {
        "status": "queued",
        "data": {
            "vin": vin,
            "make": make,
            "model": model,
            "dtc_codes": dtcs,
            "symptom_text": symptom_text
        }
    }
    
    # Normally we'd dispatch a Celery task here or similar background task,
    # but the orchestrator will be run on demand when the GET /events endpoint is called 
    # or via a background task that writes to a pubsub queue. 
    # For SSE streaming, executing during the GET request stream is the simplest non-over-engineered approach.
    
    return {"job_id": job_id, "status": "queued"}

@router.get("/diagnoses/{job_id}/events")
async def stream_diagnosis_events(job_id: str):
    """
    Step 2: Client connects via EventSource to listen to the agent's reasoning.
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job_data = job_store[job_id]["data"]
    orchestrator = ReActOrchestrator()
    
    async def event_generator():
        # Yield initial heartbeat
        yield "event: heartbeat\ndata: {}\n\n"
        
        # Run orchestrator synchronously in an async wrapper (or run_in_executor)
        # Using simple iteration for the mock
        for sse_json in orchestrator.run_diagnosis(job_data):
            # Parse the internal json to format as SSE
            event_obj = json.loads(sse_json)
            yield f"event: {event_obj['event']}\ndata: {json.dumps(event_obj['data'])}\n\n"
            await asyncio.sleep(0.1) # Small delay to ensure flush
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/diagnoses/{job_id}/approve")
async def approve_diagnosis(job_id: str, notes: str = Form(...)):
    """Senior technician approval gate (M3)."""
    return {"status": "approved", "job_id": job_id}

@router.post("/diagnoses/{job_id}/feedback")
async def submit_feedback(job_id: str, confirmed_fix: str = Form(...)):
    """Technician confirmed fix (M7)."""
    return {"status": "feedback_saved", "job_id": job_id}
