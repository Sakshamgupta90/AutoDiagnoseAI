"""Load the Zenodo Automotive Faults Dataset (record 15626055, CC BY 4.0) into Chroma.

Run manually with `python -m src.knowledge.ingest`; the API also runs it on
startup when the knowledge collection is empty.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.knowledge.vector_store import KNOWLEDGE, VectorStore, get_store

logger = logging.getLogger(__name__)

DATASET_FILE = "automotive_faults_aktc_obike_et_al.json"
FLOWCHART_FILE = "flowcharts.json"
ZENODO_SOURCE = "Zenodo AFD"


def record_chunks(records: list[dict[str, Any]]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """One chunk per fault record: category › subcategory, symptoms, and each diagnosis step with its outcomes."""
    ids, texts, metas = [], [], []
    for i, r in enumerate(records, start=1):
        steps = "; ".join(
            f"{n}) {s['step']} (possible results: {' / '.join(s.get('result', []))})"
            for n, s in enumerate(r.get("diagnosis_steps", []), start=1)
        )
        text = (
            f"{r['category']} › {r['subcategory']}. "
            f"Symptoms: {'; '.join(r.get('symptoms', []))}. "
            f"Diagnosis steps: {steps}."
        )
        ids.append(f"afd-{i:03d}")
        texts.append(text)
        metas.append({
            "source": ZENODO_SOURCE,
            "category": r["category"],
            "subcategory": r["subcategory"],
            "kind": "fault_record",
            "trust": "verified",
            "tests": json.dumps([
                f"{s['step']} — expected findings: {' / '.join(s.get('result', []))}" for s in r.get("diagnosis_steps", [])
            ]),
        })
    return ids, texts, metas


def flowchart_chunks(data: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """One chunk per decision node, linked to its flowchart and position (the 'graph' edges)."""
    ids, texts, metas = [], [], []
    for fc in data["flowcharts"]:
        node_ids = {n["id"] for n in fc["nodes"]}
        for order, node in enumerate(fc["nodes"], start=1):
            outcomes = "; ".join(
                f"if {result.lower()} → {'next: ' + next(n['check'] for n in fc['nodes'] if n['id'] == action) if action in node_ids else action}"
                for result, action in node["next"].items()
            )
            text = (
                f"{fc['title']} flowchart, symptom '{fc['expanded_branch']}', step {order}: "
                f"{node['check']}. Outcomes: {outcomes}. "
                f"Other symptom branches in this chart: {', '.join(b for b in fc['symptom_branches'] if b != fc['expanded_branch']) or 'none'}."
            )
            ids.append(node["id"])
            texts.append(text)
            metas.append({
                "source": f"Flowchart · {fc['title']}",
                "category": fc["category"],
                "subcategory": fc["expanded_branch"],
                "kind": "flowchart_step",
                "flowchart": fc["id"],
                "order": order,
                "trust": "verified",
                "tests": json.dumps([f"{node['check']} — {outcomes}"]),
            })
    return ids, texts, metas


def ingest(store: VectorStore | None = None, data_dir: Path | None = None) -> int:
    store = store or get_store()
    data_dir = data_dir or settings.DATA_DIR / "zenodo"
    records = json.loads((data_dir / DATASET_FILE).read_text(encoding="utf-8"))
    flowcharts = json.loads((data_dir / FLOWCHART_FILE).read_text(encoding="utf-8"))

    total = 0
    for ids, texts, metas in (record_chunks(records), flowchart_chunks(flowcharts)):
        store.upsert(KNOWLEDGE, ids, texts, metas)
        total += len(ids)
    logger.info("Ingested %d knowledge chunks into Chroma", total)
    return total


def ensure_ingested(store: VectorStore | None = None) -> None:
    store = store or get_store()
    if store.knowledge.count() == 0:
        ingest(store)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = ingest()
    print(f"Ingested {count} chunks. Collections: {get_store().counts()}")
