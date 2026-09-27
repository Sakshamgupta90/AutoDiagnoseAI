import itertools
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.config import settings
from src.knowledge.ingest import ingest
from src.knowledge.vector_store import get_store
from src.llm.claude import LLMUnavailable, Usage
from src.storage import db


@pytest.fixture(scope="session", autouse=True)
def isolated_data(tmp_path_factory):
    """Point SQLite and Chroma at temp dirs and load the real Zenodo dataset once."""
    root = tmp_path_factory.mktemp("data")
    settings.SQLITE_PATH = root / "test.db"
    settings.CHROMA_DIR = root / "chroma"
    settings.NHTSA_ENABLED = False
    db.connect(settings.SQLITE_PATH)
    ingest(get_store(settings.CHROMA_DIR))
    yield


_ids = itertools.count(1)


def tool_use(name: str, payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=f"toolu_{next(_ids)}", name=name, input=payload)


def response(*blocks: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason="tool_use",
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=200))


class FakeClaude:
    """Scripted stand-in for ClaudeClient: returns queued responses in order."""

    model = "fake-claude"
    enabled = True

    def __init__(self, *responses: SimpleNamespace, unavailable: str | None = None):
        self.responses = list(responses)
        self.unavailable = unavailable
        self.calls: list[dict[str, Any]] = []

    async def create(self, usage: Usage, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.unavailable:
            raise LLMUnavailable(self.unavailable)
        usage.add(1000, 200)
        return self.responses.pop(0)


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def __call__(self, type_: str, data: dict) -> None:
        self.events.append((type_, data))

    def of(self, type_: str) -> list[dict]:
        return [d for t, d in self.events if t == type_]

    @property
    def done(self) -> dict:
        return self.of("done")[-1]
