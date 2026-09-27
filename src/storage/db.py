"""SQLite persistence: jobs, diagnoses, approvals, feedback (Section 5.3), plus chat
sessions, photo findings and daily token spend."""

import json
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    vin TEXT,
    make TEXT,
    model TEXT,
    dtc_codes TEXT,
    symptom_text TEXT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_vin ON jobs (vin);
CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs (session_id);

CREATE TABLE IF NOT EXISTS diagnoses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs (id),
    result TEXT NOT NULL,            -- full final diagnosis object (JSON)
    ranked_causes TEXT,              -- JSON
    confidence REAL,
    sources TEXT,                    -- JSON
    escalation_flag INTEGER,
    answer_source TEXT,              -- knowledge_base | general_knowledge | mixed | fallback
    model_id TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs (id),
    technician_id TEXT,
    decision TEXT,
    notes TEXT,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs (id),
    confirmed_cause TEXT,
    confirmed_fix TEXT,
    part_cost REAL,
    labour_hours REAL,
    created_at TEXT NOT NULL
);

-- Chat memory: one row per user turn / assistant answer in a session.
CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    job_id TEXT,
    role TEXT NOT NULL,              -- user | assistant
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_messages ON session_messages (session_id, id);

-- What Claude saw in each uploaded photo, reused by later turns of the same chat.
CREATE TABLE IF NOT EXISTS session_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    job_id TEXT,
    filename TEXT,
    findings TEXT NOT NULL,          -- JSON
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_images ON session_images (session_id, id);

CREATE TABLE IF NOT EXISTS usage_daily (
    day TEXT PRIMARY KEY,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    calls INTEGER NOT NULL DEFAULT 0
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (or reuse) the shared connection and make sure the schema exists."""
    global _conn
    with _lock:
        if _conn is None or path is not None:
            db_path = Path(path or settings.SQLITE_PATH)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
            _conn = conn
        return _conn


def _exec(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        conn = connect()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur


def _rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in connect().execute(sql, params).fetchall()]


def _row(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    rows = _rows(sql, params)
    return rows[0] if rows else None


# ---------- jobs ----------

def create_job(job_id: str, session_id: str | None, vin: str | None, make: str | None, model: str | None,
               dtc_codes: list[str], symptom_text: str) -> None:
    _exec(
        "INSERT INTO jobs (id, session_id, vin, make, model, dtc_codes, symptom_text, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
        (job_id, session_id, vin, make, model, json.dumps(dtc_codes), symptom_text, now_iso()),
    )


def update_job_status(job_id: str, status: str, error: str | None = None) -> None:
    closed = now_iso() if status in ("closed", "rejected") else None
    _exec(
        "UPDATE jobs SET status = ?, error = COALESCE(?, error), closed_at = COALESCE(?, closed_at) WHERE id = ?",
        (status, error, closed, job_id),
    )


def update_job_vehicle(job_id: str, make: str | None, model: str | None) -> None:
    _exec("UPDATE jobs SET make = COALESCE(make, ?), model = COALESCE(model, ?) WHERE id = ?", (make, model, job_id))


def get_job(job_id: str) -> dict[str, Any] | None:
    return _row("SELECT * FROM jobs WHERE id = ?", (job_id,))


# ---------- diagnoses / audit ----------

def save_diagnosis(job_id: str, result: dict[str, Any], *, answer_source: str, model_id: str | None,
                   tokens_in: int, tokens_out: int, cost_usd: float, latency_ms: int) -> None:
    causes = result.get("ranked_causes", [])
    sources = sorted({f"{e['source']}:{e['chunk_id']}" for c in causes for e in c.get("evidence", [])})
    _exec(
        "INSERT OR REPLACE INTO diagnoses (job_id, result, ranked_causes, confidence, sources, escalation_flag,"
        " answer_source, model_id, tokens_in, tokens_out, cost_usd, latency_ms, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_id, json.dumps(result), json.dumps(causes), causes[0]["confidence"] if causes else 0.0,
            json.dumps(sources), int(bool(result.get("escalation_required"))), answer_source, model_id,
            tokens_in, tokens_out, cost_usd, latency_ms, now_iso(),
        ),
    )


def get_diagnosis(job_id: str) -> dict[str, Any] | None:
    row = _row("SELECT result FROM diagnoses WHERE job_id = ?", (job_id,))
    return json.loads(row["result"]) if row else None


def save_approval(job_id: str, technician_id: str, decision: str, notes: str | None) -> None:
    _exec(
        "INSERT INTO approvals (job_id, technician_id, decision, notes, decided_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, technician_id, decision, notes, now_iso()),
    )


def latest_decision(job_id: str) -> dict[str, Any] | None:
    return _row("SELECT * FROM approvals WHERE job_id = ? ORDER BY id DESC LIMIT 1", (job_id,))


def save_feedback(job_id: str, confirmed_cause: str, confirmed_fix: str,
                  part_cost: float | None, labour_hours: float | None) -> None:
    _exec(
        "INSERT INTO feedback (job_id, confirmed_cause, confirmed_fix, part_cost, labour_hours, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, confirmed_cause, confirmed_fix, part_cost, labour_hours, now_iso()),
    )


def service_history(vin: str, limit: int = 5) -> list[dict[str, Any]]:
    """Past closed jobs for this VIN with the technician-confirmed fix."""
    return _rows(
        "SELECT j.id AS job_id, j.created_at, j.symptom_text, f.confirmed_cause, f.confirmed_fix, f.labour_hours"
        " FROM jobs j JOIN feedback f ON f.job_id = j.id WHERE j.vin = ? ORDER BY j.created_at DESC LIMIT ?",
        (vin, limit),
    )


# ---------- chat memory ----------

def add_session_message(session_id: str, job_id: str | None, role: str, content: str) -> None:
    _exec(
        "INSERT INTO session_messages (session_id, job_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, job_id, role, content, now_iso()),
    )


def session_messages(session_id: str, limit: int = 12) -> list[dict[str, Any]]:
    rows = _rows(
        "SELECT role, content, job_id FROM session_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    )
    return list(reversed(rows))


def add_session_image(session_id: str, job_id: str, filename: str, findings: dict[str, Any]) -> None:
    _exec(
        "INSERT INTO session_images (session_id, job_id, filename, findings, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, job_id, filename, json.dumps(findings), now_iso()),
    )


def session_images(session_id: str, limit: int = 4) -> list[dict[str, Any]]:
    rows = _rows(
        "SELECT job_id, filename, findings, created_at FROM session_images WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    )
    for r in rows:
        r["findings"] = json.loads(r["findings"])
    return rows


# ---------- cost tracking ----------

def record_usage(tokens_in: int, tokens_out: int, cost_usd: float) -> None:
    _exec(
        "INSERT INTO usage_daily (day, tokens_in, tokens_out, cost_usd, calls) VALUES (?, ?, ?, ?, 1)"
        " ON CONFLICT(day) DO UPDATE SET tokens_in = tokens_in + excluded.tokens_in,"
        " tokens_out = tokens_out + excluded.tokens_out, cost_usd = cost_usd + excluded.cost_usd, calls = calls + 1",
        (date.today().isoformat(), tokens_in, tokens_out, cost_usd),
    )


def spend_today() -> dict[str, Any]:
    row = _row("SELECT * FROM usage_daily WHERE day = ?", (date.today().isoformat(),))
    return row or {"day": date.today().isoformat(), "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0}


def stats() -> dict[str, Any]:
    row = _row(
        "SELECT COUNT(*) AS diagnoses, AVG(latency_ms) AS avg_latency_ms, AVG(cost_usd) AS avg_cost_usd,"
        " SUM(CASE WHEN answer_source = 'knowledge_base' THEN 1 ELSE 0 END) AS grounded"
        " FROM diagnoses"
    ) or {}
    row["feedback"] = (_row("SELECT COUNT(*) AS n FROM feedback") or {}).get("n", 0)
    return row
