import cv2
import numpy as np
import pytest

from src.agents.orchestrator import Diagnoser, JobInput, promote_confirmed_fix
from src.knowledge.vector_store import get_store
from src.storage import db
from tests.conftest import FakeClaude, Recorder, response, tool_use


def new_job(job_id: str, text: str, **kw) -> JobInput:
    inp = JobInput(job_id=job_id, symptom_text=text, **kw)
    db.create_job(job_id, inp.session_id, inp.vin, inp.make, inp.model, inp.dtc_codes, text)
    return inp


def jpeg_bytes() -> bytes:
    img = np.full((600, 900, 3), 90, np.uint8)
    cv2.putText(img, "BRAKE", (200, 320), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 8)
    return cv2.imencode(".jpg", img)[1].tobytes()


SUBMIT_BRAKES = {
    "summary": "Pads are worn to the backing plate.",
    "answer_source": "knowledge_base",
    "ranked_causes": [
        {"cause": "Worn front brake pads", "confidence": 0.82, "evidence_ids": ["afd-003", "photo-1", "afd-999"]},
        {"cause": "Air in brake lines", "confidence": 0.4, "evidence_ids": ["fc-brake-2"]},
    ],
    "confirmation_tests": ["Measure pad thickness"],
    "parts_estimate": [{"part": "Front pad set", "est_cost": 95}],
    "labour_estimate_hours": 1.5,
    "safety_category": "brakes",
    "safety_flags": [],
}

PHOTO = {
    "summary": "Front brake assembly with heavily scored rotor.",
    "components": ["brake rotor", "caliper"],
    "abnormalities": ["deep scoring on rotor", "pad material nearly gone"],
    "warning_lights": [],
    "safety_concern": True,
    "image_quality": "good",
}


@pytest.mark.asyncio
async def test_llm_flow_cites_only_known_evidence_and_escalates_brakes():
    llm = FakeClaude(
        response(tool_use("record_photo_findings", PHOTO)),
        response(tool_use("knowledge_search", {"query": "brake pedal soft grinding noise"})),
        response(tool_use("submit_diagnosis", SUBMIT_BRAKES)),
    )
    rec = Recorder()
    inp = new_job("job_t1", "Spongy brake pedal and grinding noise when stopping", session_id="s1",
                  make="Honda", model="Civic", photos=[("brake.jpg", jpeg_bytes())])
    await Diagnoser(inp, rec, llm=llm).run()

    tools = [s["tool_used"] for s in rec.of("step")]
    assert tools == ["photo_analysis", "knowledge_search", "knowledge_search"]
    assert [s["step_no"] for s in rec.of("step")] == [1, 2, 3]  # unique per tool call

    done = rec.done
    cited = [e["chunk_id"] for e in done["ranked_causes"][0]["evidence"]]
    assert "afd-999" not in cited and "afd-003" in cited and "photo-1" in cited
    assert done["escalation_required"] is True
    assert rec.of("escalation")[0]["category"] == "brakes"
    assert "Safety concern visible in photo" in done["safety_flags"]
    assert done["fallback_mode"] is False
    # last agent call is forced to submit
    assert llm.calls[1]["tool_choice"] == {"type": "auto"}
    assert db.get_job("job_t1")["status"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_follow_up_reuses_photo_from_same_chat():
    llm = FakeClaude(response(tool_use("submit_diagnosis", {**SUBMIT_BRAKES, "safety_category": "brakes"})))
    rec = Recorder()
    inp = new_job("job_t2", "It also pulls to the left when braking", session_id="s1")
    await Diagnoser(inp, rec, llm=llm).run()

    steps = rec.of("step")
    assert steps[0]["tool_used"] == "photo_analysis" and "reused" in steps[0]["key_inputs"]
    assert any(e["source"] == "Earlier photo (this chat)" for e in rec.of("evidence"))
    context = llm.calls[0]["messages"][0]["content"]
    assert "from an earlier message in this chat" in context
    assert "Spongy brake pedal" in context  # conversation memory


@pytest.mark.asyncio
async def test_fallback_when_bedrock_unavailable():
    rec = Recorder()
    inp = new_job("job_t3", "Brake pedal feels soft and sinks to the floor")
    await Diagnoser(inp, rec, llm=FakeClaude(unavailable="Can't reach AWS Bedrock.")).run()

    assert rec.of("notice")[0]["kind"] == "cloud_unreachable"
    done = rec.done
    assert done["fallback_mode"] is True
    assert "brake" in done["ranked_causes"][0]["cause"].lower()
    assert done["confirmation_tests"]
    assert done["escalation_required"] is True  # brakes category


@pytest.mark.asyncio
async def test_knowledge_gap_is_learned_then_confirmed():
    store = get_store()
    submit = {
        "summary": "Head unit firmware crash.",
        "answer_source": "general_knowledge",
        "ranked_causes": [{"cause": "Infotainment head unit firmware fault", "confidence": 0.6, "evidence_ids": []}],
        "confirmation_tests": ["Hard-reset the head unit", "Check for a firmware update"],
        "parts_estimate": [],
        "labour_estimate_hours": 0.5,
        "safety_category": "none",
        "safety_flags": [],
    }
    before = store.counts()
    rec = Recorder()
    inp = new_job("job_t4", "Infotainment screen freezes and bluetooth will not pair")
    await Diagnoser(inp, rec, llm=FakeClaude(response(tool_use("submit_diagnosis", submit)))).run()

    assert rec.of("notice")[0]["kind"] == "knowledge_gap"
    assert rec.done["answer_source"] == "general_knowledge"
    assert store.counts()["learned_unverified"] == before["learned_unverified"] + 1

    promote_confirmed_fix(db.get_job("job_t4"), "Head unit firmware fault", "Flashed latest firmware")
    counts = store.counts()
    assert counts["learned_unverified"] == before["learned_unverified"]
    assert counts["learned_confirmed"] == before["learned_confirmed"] + 1
    top = store.search("infotainment screen frozen, bluetooth pairing fails", top_k=1)[0]
    assert top.trust == "confirmed"


@pytest.mark.asyncio
async def test_offline_vague_photo_question_is_consistent():
    """Regression: offline + vague text + photo must not claim a general-knowledge answer was saved."""
    rec = Recorder()
    inp = new_job("job_t5", "whats the symptom", photos=[("leak.jpg", jpeg_bytes())])
    await Diagnoser(inp, rec, llm=FakeClaude(unavailable="AI model disabled (LLM_ENABLED=false).")).run()

    kinds = [n["kind"] for n in rec.of("notice")]
    assert "knowledge_gap" not in kinds and "cloud_unreachable" in kinds
    done = rec.done
    assert done["fallback_mode"] is True
    assert "Photos can't be analysed" in done["summary"]
    assert done["escalation_type"] == "low_confidence"


@pytest.mark.asyncio
async def test_confirmed_fix_ranks_first_and_drives_offline_answer():
    store = get_store()
    db.create_job("job_t6", None, None, "Hyundai", "Elantra", ["P0217"], "Temperature gauge climbs into the red in traffic")
    promote_confirmed_fix(db.get_job("job_t6"), "Leaking lower radiator hose", "Replaced lower radiator hose")
    top = store.search("Temperature gauge climbs into the red in traffic and coolant keeps dropping", top_k=3)[0]
    assert top.trust == "confirmed"

    rec = Recorder()
    inp = new_job("job_t7", "Temperature gauge climbs into the red in traffic and coolant keeps dropping")
    await Diagnoser(inp, rec, llm=FakeClaude(unavailable="offline")).run()
    done = rec.done
    assert "Replaced lower radiator hose" in done["ranked_causes"][0]["cause"]
    assert done["ranked_causes"][0]["confidence"] >= 0.5
    assert "confirmed at this workshop" in done["summary"]
