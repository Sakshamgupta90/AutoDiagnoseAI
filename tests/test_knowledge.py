from src.knowledge.dtc import describe_dtc
from src.knowledge.vector_store import get_store


def test_dtc_descriptions():
    assert "Cylinder 3 misfire" in describe_dtc("P0303")
    assert "lean" in describe_dtc("p0171").lower()
    assert "ignition system or misfire" in describe_dtc("P0351")
    assert "unrecognised" in describe_dtc("X123")


def test_semantic_search_matches_dataset():
    hits = get_store().search("brake pedal feels soft and spongy", top_k=3)
    assert hits[0].category == "ABS System"
    assert hits[0].similarity > 0.5


def test_unrelated_query_scores_low():
    hits = get_store().search("infotainment screen frozen and bluetooth won't pair", top_k=1)
    assert hits[0].similarity < 0.4


def test_flowchart_expansion_returns_decision_path():
    store = get_store()
    hit = next(h for h in store.search("engine overheating check coolant level radiator fan thermostat", top_k=5) if h.metadata.get("flowchart"))
    related = store.related(hit)
    assert {n.metadata["flowchart"] for n in related} == {"overheating"}
    assert len(related) >= 3
