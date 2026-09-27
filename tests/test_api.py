"""End-to-end over HTTP, exactly as the frontend calls it (Bedrock disabled -> local fallback)."""

import json

import pytest
from fastapi.testclient import TestClient

from src.core.config import settings
from src.main import app


@pytest.fixture(scope="module")
def client():
    settings.LLM_ENABLED = False
    with TestClient(app) as c:
        yield c
    settings.LLM_ENABLED = True


def read_events(client: TestClient, job_id: str, last_event_id: str | None = None) -> list[tuple[str | None, str, dict]]:
    headers = {"Accept": "text/event-stream", **({"Last-Event-ID": last_event_id} if last_event_id else {})}
    events, cur = [], {}
    with client.stream("GET", f"/api/v1/diagnoses/{job_id}/events", headers=headers) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        for line in res.iter_lines():
            if line.startswith(":"):
                continue
            if not line:
                if cur.get("event"):
                    events.append((cur.get("id"), cur["event"], json.loads(cur["data"])))
                cur = {}
                continue
            field, _, value = line.partition(": ")
            cur[field] = value
    return events


def test_full_job_lifecycle(client):
    res = client.post(
        "/api/v1/diagnoses",
        data={"symptom_text": "Engine overheating in traffic, coolant level keeps dropping", "make": "Hyundai",
              "model": "Elantra", "dtc_codes": ["P0217", "p0128"], "session_id": "chat-1"},
    )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    events = read_events(client, job_id)
    types = [t for _, t, _ in events]
    assert types[0] == "notice" or "step" in types
    assert types[-1] == "done"
    assert "evidence" in types and "confidence" in types
    done = events[-1][2]
    assert done["job_id"] == job_id and done["fallback_mode"] is True
    assert done["ranked_causes"][0]["evidence"]

    # Reconnect with Last-Event-ID replays only the tail, without re-running the job
    tail = read_events(client, job_id, last_event_id=events[-3][0])
    assert [t for _, t, _ in tail] == [t for _, t, _ in events[-2:]]

    snap = client.get(f"/api/v1/diagnoses/{job_id}").json()
    assert snap["diagnosis"]["job_id"] == job_id

    assert client.post(f"/api/v1/diagnoses/{job_id}/approve", json={"technician_id": "T-014"}).json()["status"] == "approved"
    fb = client.post(f"/api/v1/diagnoses/{job_id}/feedback",
                     json={"confirmed_cause": "Thermostat stuck closed", "confirmed_fix": "Replaced thermostat", "labour_hours": 1.2})
    assert fb.status_code == 200 and fb.json()["knowledge_base"]["learned_confirmed"] >= 1
    assert client.get(f"/api/v1/diagnoses/{job_id}").json()["status"] == "closed"


def test_validation_errors(client):
    bad = client.post("/api/v1/diagnoses", data={"symptom_text": "Rough idle", "dtc_codes": ["P9ZZZ"]})
    assert bad.status_code == 422 and "OBD-II" in bad.json()["detail"]
    assert client.post("/api/v1/diagnoses", data={"symptom_text": "x"}).status_code == 422
    assert client.get("/api/v1/diagnoses/job_missing").status_code == 404
    assert client.post("/api/v1/diagnoses/job_missing/approve", json={"technician_id": "T-1"}).status_code == 404


def test_health(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["knowledge_base"]["knowledge"] == 114
