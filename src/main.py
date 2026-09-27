import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import diagnose
from src.core.config import settings
from src.knowledge.ingest import ensure_ingested
from src.knowledge.vector_store import get_store
from src.storage import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("autodiagnose")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.connect()
    store = get_store()
    await asyncio.to_thread(ensure_ingested, store)
    logger.info("Knowledge base ready: %s", store.counts())
    if not settings.has_aws_credentials:
        logger.warning("No AWS credentials in .env — Bedrock calls will use the default AWS chain or fall back to local mode.")
    yield


app = FastAPI(
    title="AutoDiagnose AI Backend",
    description="Agentic backend for vehicle fault diagnosis: RAG over the Zenodo faults dataset, Claude on Bedrock, human-in-the-loop.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(diagnose.router, prefix="/api/v1")


@app.get("/health")
def root_health() -> dict:
    return {"status": "ok", "service": "AutoDiagnoseAI-Backend"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
