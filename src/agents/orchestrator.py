"""Diagnostic agent: context gathering, retrieval, a budgeted Claude tool-use loop,
safety escalation, and the local fallback when Bedrock is unavailable.

Emits the typed SSE events from the frozen contract (Section 6.2):
step, evidence, confidence, escalation, notice, done.
"""

import asyncio
import base64
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from src.agents.prompts import AGENT_TOOLS, PHOTO_FINDINGS_TOOL, PHOTO_PROMPT, SYSTEM_PROMPT
from src.core.config import settings
from src.knowledge.dtc import describe_all
from src.knowledge.vector_store import LEARNED, Hit, VectorStore, get_store
from src.llm.claude import ClaudeClient, LLMUnavailable, Usage, claude
from src.storage import db
from src.tools.image_processing import prepare_image_for_vision_model
from src.tools.vin_decoder import decode_vin, describe_vehicle

logger = logging.getLogger(__name__)

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]

# Server-side safety guard on top of the model's own classification (Section 7.1).
SAFETY_KEYWORDS = {
    "brakes": re.compile(r"\b(brake|abs\b|caliper|rotor|brake pad|master cylinder|brake fluid|brake booster)", re.I),
    "steering": re.compile(r"\b(steering|tie rod|rack and pinion|power steering)", re.I),
    "airbags": re.compile(r"\b(airbag|srs\b|clockspring|seat ?belt pretensioner)", re.I),
    "ev_high_voltage": re.compile(r"\b(high[- ]voltage|traction battery|hybrid battery|hv battery|inverter|orange cabl)", re.I),
}
CATEGORY_SAFETY = {"ABS System": "brakes", "Brakes": "brakes", "Steering": "steering"}
SAFETY_LABELS = {
    "brakes": "Brake system",
    "steering": "Steering system",
    "airbags": "Airbag / SRS",
    "ev_high_voltage": "EV / hybrid high voltage",
}


@dataclass
class JobInput:
    job_id: str
    symptom_text: str
    dtc_codes: list[str] = field(default_factory=list)
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    session_id: str | None = None
    photos: list[tuple[str, bytes]] = field(default_factory=list)


class Diagnoser:
    def __init__(self, inp: JobInput, emit: Emit, llm: ClaudeClient | None = None, store: VectorStore | None = None):
        self.inp = inp
        self._emit = emit
        self.llm = llm or claude
        self.store = store or get_store()
        self.usage = Usage()
        self.started = time.monotonic()
        self.deadline = self.started + settings.JOB_TIME_BUDGET_SECONDS
        self.step_no = 0
        self.tool_calls = 0
        self.registry: dict[str, dict[str, str]] = {}  # citable id -> {source, chunk_id}
        self.hits: dict[str, Hit] = {}
        self.best_similarity = 0.0
        self.vehicle: dict[str, Any] = {}
        self.photo_findings: list[dict[str, Any]] = []
        self.history: list[dict[str, Any]] = []
        self.dtc_text = describe_all(inp.dtc_codes)
        self.llm_error: LLMUnavailable | None = None
        self.notices: set[str] = set()

    # ---------- event helpers ----------

    async def emit(self, type_: str, data: dict[str, Any]) -> None:
        await self._emit(type_, data)

    async def step(self, tool: str, key_inputs: dict[str, Any], turn: int) -> None:
        self.step_no += 1
        await self.emit("step", {"step_no": self.step_no, "tool_used": tool, "key_inputs": key_inputs, "turn": turn})

    async def evidence(self, cite_id: str, source: str, chunk_id: str, snippet: str) -> None:
        self.registry[cite_id] = {"source": source, "chunk_id": chunk_id}
        await self.emit("evidence", {"source": source, "chunk_id": chunk_id, "snippet_ref": snippet[:280]})

    async def notice(self, kind: str, message: str) -> None:
        if kind not in self.notices:
            self.notices.add(kind)
            await self.emit("notice", {"kind": kind, "message": message})

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    # ---------- main flow ----------

    async def run(self) -> dict[str, Any]:
        inp = self.inp
        prior = db.session_messages(inp.session_id) if inp.session_id else []
        if inp.session_id:
            db.add_session_message(inp.session_id, inp.job_id, "user", self._user_turn_text())

        await self._vehicle_step()
        await self._photo_step()
        await self._history_step()
        await self._retrieval_step(prior)

        if self.llm_error is None:
            try:
                raw = await self._agent_loop(prior)
                if raw is not None:
                    return await self.finalize(raw, mode="llm")
                await self.notice("budget_exhausted", "Reasoning budget reached before a final answer. Showing the tests to run first.")
                return await self.finalize(self._fallback_raw(), mode="fallback", budget_exhausted=True)
            except LLMUnavailable as exc:
                self.llm_error = exc
            except TimeoutError:
                await self.notice("budget_exhausted", f"The {int(settings.JOB_TIME_BUDGET_SECONDS)}s time budget ran out. Showing the tests to run first.")
                return await self.finalize(self._fallback_raw(), mode="fallback", budget_exhausted=True)

        await self._cloud_notice()
        return await self.finalize(self._fallback_raw(), mode="fallback")

    async def _cloud_notice(self) -> None:
        reason = self.llm_error.reason if self.llm_error else "AI model unavailable."
        await self.notice("cloud_unreachable", f"{reason} Using the local knowledge-base fallback — results are less precise.")

    def _user_turn_text(self) -> str:
        inp = self.inp
        extras = []
        if inp.make or inp.model:
            extras.append(f"vehicle: {' '.join(p for p in (inp.make, inp.model) if p)}")
        if inp.dtc_codes:
            extras.append(f"codes: {', '.join(inp.dtc_codes)}")
        if inp.photos:
            extras.append(f"{len(inp.photos)} photo(s)")
        return inp.symptom_text + (f" [{'; '.join(extras)}]" if extras else "")

    # ---------- context gathering ----------

    async def _vehicle_step(self) -> None:
        inp = self.inp
        self.vehicle = {"make": inp.make, "model": inp.model}
        if not inp.vin:
            return
        await self.step("vin_decode", {"vin": inp.vin}, turn=1)
        decoded = await decode_vin(inp.vin)
        if decoded.get("ok"):
            self.vehicle = {**decoded, "make": inp.make or decoded.get("make"), "model": inp.model or decoded.get("model")}
            db.update_job_vehicle(inp.job_id, self.vehicle.get("make"), self.vehicle.get("model"))
            await self.evidence("vin", "NHTSA vPIC", f"vin:{inp.vin}", describe_vehicle(decoded))
        else:
            self.vehicle["note"] = decoded.get("reason")
            await self.evidence("vin", "Vehicle", "manual-entry", decoded.get("reason", ""))

    async def _photo_step(self) -> None:
        inp = self.inp
        if inp.photos:
            await self.step("photo_analysis", {"photos": len(inp.photos), "model": "claude-sonnet-4.5"}, turn=1)
            for i, (filename, raw) in enumerate(inp.photos, start=1):
                cite = f"photo-{i}"
                try:
                    jpeg = await asyncio.to_thread(prepare_image_for_vision_model, raw, 1024, 80)
                except ValueError:
                    await self.evidence(cite, "Inspection photo", cite, f"{filename}: could not be read as an image.")
                    continue
                findings = await self._analyse_photo(jpeg)
                if findings is None:
                    await self.evidence(cite, "Inspection photo", cite, f"{filename}: received, but AI vision is unavailable.")
                    continue
                self.photo_findings.append({"id": cite, "filename": filename, "findings": findings, "reused": False})
                if inp.session_id:
                    db.add_session_image(inp.session_id, inp.job_id, filename, findings)
                issues = "; ".join(findings.get("abnormalities") or []) or "no visible abnormality"
                await self.evidence(cite, "Inspection photo", cite, f"{findings.get('summary', '')} Findings: {issues}.")
        elif inp.session_id:
            earlier = db.session_images(inp.session_id, limit=2)
            if earlier:
                await self.step("photo_analysis", {"reused": f"{len(earlier)} earlier photo(s) from this chat"}, turn=1)
                for i, img in enumerate(earlier, start=1):
                    cite = f"photo-{i}"
                    self.photo_findings.append({"id": cite, "filename": img["filename"], "findings": img["findings"], "reused": True})
                    await self.evidence(cite, "Earlier photo (this chat)", cite, img["findings"].get("summary", ""))

    async def _analyse_photo(self, jpeg: bytes) -> dict[str, Any] | None:
        if self.llm_error is not None:
            return None
        note = self.inp.symptom_text[:500]
        try:
            msg = await asyncio.wait_for(
                self.llm.create(
                    self.usage,
                    max_tokens=600,
                    system=PHOTO_PROMPT,
                    tools=[PHOTO_FINDINGS_TOOL],
                    tool_choice={"type": "tool", "name": "record_photo_findings"},
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
                            {"type": "text", "text": f"Technician's note:\n<technician_input>{note}</technician_input>"},
                        ],
                    }],
                ),
                timeout=max(5.0, min(20.0, self.remaining() - 10)),
            )
        except LLMUnavailable as exc:
            self.llm_error = exc
            return None
        except TimeoutError:
            return None
        block = next((b for b in msg.content if b.type == "tool_use"), None)
        return dict(block.input) if block else None

    async def _history_step(self) -> None:
        if not self.inp.vin:
            return
        await self.step("sqlite_history", {"vin": self.inp.vin, "lookback": "last 5 closed jobs"}, turn=1)
        self.history = db.service_history(self.inp.vin)
        for row in self.history:
            await self.evidence(
                f"history-{row['job_id']}", "Service history", row["job_id"],
                f"{row['created_at'][:10]}: {row['confirmed_cause']} — {row['confirmed_fix']}",
            )

    def _build_query(self, prior: list[dict[str, Any]]) -> str:
        parts = [self.inp.symptom_text]
        parts += [d.split(": ", 1)[-1] for d in self.dtc_text]
        for p in self.photo_findings:
            f = p["findings"]
            parts.append(" ".join([f.get("summary", "")] + list(f.get("abnormalities") or [])))
        previous_user = [m["content"] for m in prior if m["role"] == "user"]
        if previous_user:
            parts.append(previous_user[-1])
        return ". ".join(p.strip() for p in parts if p and p.strip())[:1000]

    async def _search(self, query: str, turn: int, category: str | None = None) -> list[Hit]:
        await self.step("knowledge_search", {"query": query[:90] + ("…" if len(query) > 90 else ""), **({"category": category} if category else {})}, turn=turn)
        hits = await asyncio.to_thread(self.store.search, query, settings.SEARCH_TOP_K, category)
        shown = 0
        for h in hits:
            self.hits[h.id] = h
            if h.trust != "unverified":
                self.best_similarity = max(self.best_similarity, h.similarity)
            if h.similarity >= settings.RELEVANCE_THRESHOLD and shown < 4:
                shown += 1
                label = h.source if h.trust != "unverified" else "Learned (unverified)"
                await self.evidence(h.id, label, h.id, h.text)
            else:
                self.registry.setdefault(h.id, {"source": h.source, "chunk_id": h.id})
        return hits

    async def _retrieval_step(self, prior: list[dict[str, Any]]) -> None:
        hits = await self._search(self._build_query(prior), turn=1)
        # Graph-style expansion: pull in the rest of a matching flowchart's decision path.
        top_flow = next((h for h in hits if h.metadata.get("flowchart") and h.similarity >= settings.RELEVANCE_THRESHOLD), None)
        if top_flow:
            for node in await asyncio.to_thread(self.store.related, top_flow):
                self.hits.setdefault(node.id, node)
                self.registry.setdefault(node.id, {"source": node.source, "chunk_id": node.id})
        await self.emit("confidence", {"value": self._evidence_confidence()})

    def _evidence_confidence(self) -> float:
        return round(min(0.8, 0.15 + self.best_similarity * 0.85), 2)

    # ---------- Claude tool-use loop ----------

    def _context_message(self, prior: list[dict[str, Any]]) -> str:
        inp = self.inp
        v = self.vehicle
        lines = ["<vehicle>"]
        lines.append(describe_vehicle(v) if v.get("make") else "Make/model not provided.")
        if v.get("electrification"):
            lines.append(f"Electrification: {v['electrification']}")
        if v.get("note"):
            lines.append(f"Note: {v['note']}")
        lines.append("</vehicle>")
        lines.append("Fault codes: " + ("; ".join(self.dtc_text) if self.dtc_text else "none reported"))

        if self.photo_findings:
            lines.append("<photo_findings>")
            for p in self.photo_findings:
                tag = " (from an earlier message in this chat)" if p["reused"] else ""
                lines.append(f"[{p['id']}]{tag} {json.dumps(p['findings'])}")
            lines.append("</photo_findings>")

        if prior:
            lines.append("Conversation so far (oldest first):")
            for m in prior[-8:]:
                lines.append(f"- {m['role']}: {m['content'][:400]}")

        lines.append("Service history: " + ("" if self.history else "no confirmed past jobs for this VIN."))
        for row in self.history:
            lines.append(f"[history-{row['job_id']}] {row['created_at'][:10]}: {row['confirmed_cause']} — {row['confirmed_fix']}")

        lines.append(f"Knowledge base matches (cosine similarity; ≥ {settings.RELEVANCE_THRESHOLD:.2f} counts as relevant):")
        for h in sorted(self.hits.values(), key=lambda x: x.score, reverse=True)[:10]:
            trust = " UNVERIFIED" if h.trust == "unverified" else ""
            lines.append(f"[{h.id}] ({h.similarity:.2f}, {h.source}{trust}) {h.text}")
        if self.best_similarity < settings.RELEVANCE_THRESHOLD:
            lines.append("No entry reaches the relevance threshold: search once more if useful, otherwise rely on general knowledge and set answer_source accordingly.")

        lines.append(f"<technician_input>{inp.symptom_text}</technician_input>")
        return "\n".join(lines)

    async def _agent_loop(self, prior: list[dict[str, Any]]) -> dict[str, Any] | None:
        messages: list[dict[str, Any]] = [{"role": "user", "content": self._context_message(prior)}]
        for turn in range(1, settings.MAX_TURNS + 1):
            remaining = self.remaining()
            if remaining < 4:
                return None
            force = turn == settings.MAX_TURNS or self.tool_calls >= settings.MAX_TOOL_CALLS or remaining < 15
            msg = await asyncio.wait_for(
                self.llm.create(
                    self.usage,
                    system=SYSTEM_PROMPT,
                    tools=AGENT_TOOLS,
                    tool_choice={"type": "tool", "name": "submit_diagnosis"} if force else {"type": "auto"},
                    messages=messages,
                ),
                timeout=remaining,
            )
            tool_uses = [b for b in msg.content if b.type == "tool_use"]
            submit = next((b for b in tool_uses if b.name == "submit_diagnosis"), None)
            if submit is not None:
                return dict(submit.input)

            messages.append({"role": "assistant", "content": msg.content})
            if not tool_uses:
                messages.append({"role": "user", "content": "Call submit_diagnosis now with your final answer."})
                continue

            results = []
            for tu in tool_uses:
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(await self._run_tool(tu.name, dict(tu.input), turn + 1))})
            messages.append({"role": "user", "content": results})
            await self.emit("confidence", {"value": self._evidence_confidence()})
        return None

    async def _run_tool(self, name: str, args: dict[str, Any], turn: int) -> dict[str, Any]:
        self.tool_calls += 1
        if self.tool_calls > settings.MAX_TOOL_CALLS:
            return {"error": "Tool budget exhausted. Call submit_diagnosis now."}
        if name == "knowledge_search":
            hits = await self._search(str(args.get("query", ""))[:500], turn=turn, category=args.get("category") or None)
            return {"results": [h.as_tool_result() for h in hits]}
        if name == "service_history":
            vin = str(args.get("vin") or self.inp.vin or "")
            await self.step("sqlite_history", {"vin": vin}, turn=turn)
            rows = db.service_history(vin) if vin else []
            for row in rows:
                self.registry[f"history-{row['job_id']}"] = {"source": "Service history", "chunk_id": row["job_id"]}
            return {"history": rows}
        return {"error": f"Unknown tool {name}"}

    # ---------- local fallback ----------

    def _fallback_raw(self) -> dict[str, Any]:
        """Deterministic diagnosis from the knowledge base alone (no LLM)."""
        relevant = [h for h in sorted(self.hits.values(), key=lambda x: x.score, reverse=True)
                    if h.similarity >= settings.RELEVANCE_THRESHOLD - 0.05 and h.trust != "unverified"][:3]
        if not relevant:
            return {
                "summary": "The knowledge base has no close match and the AI model is not available, so there isn't enough "
                           "evidence to name a cause. Run the general checks below and add fault codes or photos.",
                "answer_source": "fallback",
                "ranked_causes": [{"cause": "Insufficient evidence — run these tests first", "confidence": 0.2, "evidence_ids": []}],
                "confirmation_tests": [
                    "Scan all modules for stored and pending OBD-II fault codes.",
                    "Record when the symptom occurs: cold/warm engine, speed, load, weather.",
                    "Photograph any visible leaks, damage or warning lights and add them to this chat.",
                ],
                "parts_estimate": [],
                "labour_estimate_hours": 0.5,
                "safety_category": "none",
                "safety_flags": [],
            }
        causes, tests = [], []
        for h in relevant:
            label = h.metadata.get("subcategory") or h.category
            causes.append({
                "cause": f"{label} fault ({h.category})",
                "confidence": round(min(0.7, h.similarity * 0.85), 2),
                "evidence_ids": [h.id],
            })
            for t in json.loads(h.metadata.get("tests", "[]")):
                if t not in tests:
                    tests.append(t)
        top = relevant[0]
        return {
            "summary": f"Offline result from the local knowledge base. The closest match is "
                       f"“{top.metadata.get('subcategory') or top.category}” ({top.source}). "
                       "Work through the checks below; the estimate covers diagnostic time only.",
            "answer_source": "fallback",
            "ranked_causes": causes,
            "confirmation_tests": tests[:6],
            "parts_estimate": [],
            "labour_estimate_hours": 1.0,
            "safety_category": CATEGORY_SAFETY.get(top.category, "none"),
            "safety_flags": [],
        }

    # ---------- final answer ----------

    def _safety_category(self, raw: dict[str, Any], causes: list[dict[str, Any]]) -> str:
        category = raw.get("safety_category") or "none"
        if category in SAFETY_LABELS:
            return category
        text = " ".join(c["cause"] for c in causes[:2])
        for cat, pattern in SAFETY_KEYWORDS.items():
            if pattern.search(text):
                return cat
        return "none"

    async def finalize(self, raw: dict[str, Any], *, mode: str, budget_exhausted: bool = False) -> dict[str, Any]:
        inp = self.inp
        causes = []
        for c in raw.get("ranked_causes") or []:
            evidence = [self.registry[e] for e in c.get("evidence_ids", []) if e in self.registry]
            try:
                conf = float(c.get("confidence", 0))
            except (TypeError, ValueError):
                conf = 0.0
            causes.append({"cause": str(c.get("cause", "")).strip() or "Unspecified", "confidence": round(min(1.0, max(0.0, conf)), 2), "evidence": evidence})
        causes.sort(key=lambda c: c["confidence"], reverse=True)
        if not causes:
            causes = [{"cause": "Insufficient evidence — run these tests first", "confidence": 0.2, "evidence": []}]

        top_conf = causes[0]["confidence"]
        safety = self._safety_category(raw, causes)
        flags = [str(f) for f in raw.get("safety_flags") or [] if str(f).strip()]
        if safety != "none" and SAFETY_LABELS[safety] not in flags:
            flags.insert(0, SAFETY_LABELS[safety])
        if any(p["findings"].get("safety_concern") for p in self.photo_findings) and "Safety concern visible in photo" not in flags:
            flags.append("Safety concern visible in photo")

        low_conf = top_conf < settings.CONFIDENCE_THRESHOLD
        escalate = safety != "none" or low_conf
        if safety != "none":
            await self.emit("escalation", {"category": safety.replace("_", " "), "reason": f"{SAFETY_LABELS[safety]} fault — the repair plan needs senior technician sign-off before release."})
        elif low_conf:
            await self.emit("escalation", {"category": "low confidence", "reason": f"Confidence {top_conf:.0%} is below {settings.CONFIDENCE_THRESHOLD:.0%} — a senior technician should review before any repair."})

        answer_source = raw.get("answer_source") or ("fallback" if mode == "fallback" else "general_knowledge")
        if mode == "llm" and self.best_similarity < settings.RELEVANCE_THRESHOLD and answer_source == "knowledge_base":
            answer_source = "general_knowledge"
        if mode == "llm" and answer_source == "general_knowledge":
            await self.notice(
                "knowledge_gap",
                f"No close match in the workshop knowledge base (best similarity {self.best_similarity:.2f}). "
                "This answer comes from general automotive knowledge and is saved as unverified until a technician confirms the fix.",
            )

        summary = str(raw.get("summary", "")).strip()
        if mode == "fallback" and inp.photos:
            summary += " Photos can't be analysed while the AI model is offline — describe what you see in the message."

        diagnosis: dict[str, Any] = {
            "job_id": inp.job_id,
            "summary": summary,
            "ranked_causes": causes,
            "confirmation_tests": [str(t) for t in raw.get("confirmation_tests") or []][:6],
            "parts_estimate": [
                {"part": str(p.get("part", "")), "est_cost": round(float(p.get("est_cost") or 0), 2)}
                for p in raw.get("parts_estimate") or [] if p.get("part")
            ],
            "labour_estimate_hours": round(float(raw.get("labour_estimate_hours") or 0), 1),
            "safety_flags": flags,
            "escalation_required": escalate,
            # "safety" hard-blocks the plan until senior sign-off; "low_confidence" shows the tests but asks for review.
            "escalation_type": "safety" if safety != "none" else ("low_confidence" if low_conf else None),
            "answer_source": answer_source,
            "fallback_mode": mode == "fallback",
            "budget_exhausted": budget_exhausted,
        }
        await self.emit("confidence", {"value": top_conf})
        await self.emit("done", diagnosis)

        latency_ms = int((time.monotonic() - self.started) * 1000)
        db.save_diagnosis(
            inp.job_id, diagnosis, answer_source=answer_source,
            model_id=self.llm.model if self.usage.calls else None,
            tokens_in=self.usage.tokens_in, tokens_out=self.usage.tokens_out,
            cost_usd=round(self.usage.cost_usd, 6), latency_ms=latency_ms,
        )
        db.update_job_status(inp.job_id, "awaiting_approval" if escalate else "awaiting_review")
        if inp.session_id:
            summary = f"Top cause: {causes[0]['cause']} ({top_conf:.0%}). {diagnosis['summary']}"
            db.add_session_message(inp.session_id, inp.job_id, "assistant", summary[:1200])
        if mode == "llm" and answer_source == "general_knowledge":
            await asyncio.to_thread(self._save_learned, diagnosis)
        logger.info("Job %s done in %dms (mode=%s, source=%s, tokens=%d/%d, $%.4f)", inp.job_id, latency_ms, mode,
                    answer_source, self.usage.tokens_in, self.usage.tokens_out, self.usage.cost_usd)
        return diagnosis

    def _save_learned(self, diagnosis: dict[str, Any]) -> None:
        """Remember an answer that came from general knowledge — unverified until a technician confirms it."""
        inp = self.inp
        causes = "; ".join(f"{c['cause']} ({c['confidence']:.0%})" for c in diagnosis["ranked_causes"][:3])
        text = (
            f"Symptoms reported: {inp.symptom_text}. "
            + (f"Fault codes: {'; '.join(self.dtc_text)}. " if self.dtc_text else "")
            + f"Suggested causes (unverified, general knowledge): {causes}. "
            + f"First checks: {'; '.join(diagnosis['confirmation_tests'][:3])}."
        )
        self.store.upsert(LEARNED, [f"learned-{inp.job_id}"], [text], [{
            "source": "Learned (unverified)",
            "trust": "unverified",
            "category": "Learned",
            "kind": "learned_answer",
            "job_id": inp.job_id,
            "tests": json.dumps(diagnosis["confirmation_tests"][:4]),
        }])


def promote_confirmed_fix(job: dict[str, Any], confirmed_cause: str, confirmed_fix: str, store: VectorStore | None = None) -> None:
    """Feedback loop (M7): a technician-confirmed fix becomes trusted knowledge; the unverified guess is retired."""
    store = store or get_store()
    codes = json.loads(job.get("dtc_codes") or "[]")
    vehicle = " ".join(p for p in (job.get("make"), job.get("model")) if p)
    text = (
        f"Confirmed workshop fix. Symptoms: {job.get('symptom_text', '')}. "
        + (f"Fault codes: {'; '.join(describe_all(codes))}. " if codes else "")
        + (f"Vehicle: {vehicle}. " if vehicle else "")
        + f"Confirmed cause: {confirmed_cause}. Repair: {confirmed_fix}."
    )
    store.upsert(LEARNED, [f"confirmed-{job['id']}"], [text], [{
        "source": "Workshop confirmed fix",
        "trust": "confirmed",
        "category": "Confirmed fix",
        "kind": "confirmed_fix",
        "job_id": job["id"],
        "subcategory": confirmed_cause[:80],
        "tests": json.dumps([f"Verify: {confirmed_cause}", f"Previously fixed by: {confirmed_fix}"]),
    }])
    store.delete(LEARNED, [f"learned-{job['id']}"])


async def run_job(inp: JobInput, emit: Emit, llm: ClaudeClient | None = None, store: VectorStore | None = None) -> None:
    db.update_job_status(inp.job_id, "running")
    try:
        await Diagnoser(inp, emit, llm=llm, store=store).run()
    except Exception as exc:  # the stream must always end with done or error
        logger.exception("Job %s failed", inp.job_id)
        db.update_job_status(inp.job_id, "failed", error=str(exc)[:500])
        await emit("error", {"message": "The diagnosis failed unexpectedly. Please try again.", "retryable": True})
