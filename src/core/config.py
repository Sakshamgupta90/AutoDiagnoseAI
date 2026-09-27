from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All runtime configuration. Secrets come from `.env` at the repo root (never committed)."""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # --- AWS Bedrock (Claude) ---
    AWS_REGION: str = "ap-southeast-1"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_SESSION_TOKEN: str | None = None
    # Alternative to access keys: a Bedrock API key (bearer token).
    AWS_BEARER_TOKEN_BEDROCK: str | None = None
    # Sonnet 4.5 has no `apac.` inference profile; `global.` works from ap-southeast-1.
    BEDROCK_MODEL_ID: str = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    LLM_ENABLED: bool = True
    LLM_MAX_TOKENS: int = 2048
    LLM_TIMEOUT_SECONDS: float = 30.0

    # --- Cost controls (Section 7.3) ---
    PRICE_INPUT_PER_MTOK: float = 3.0
    PRICE_OUTPUT_PER_MTOK: float = 15.0
    DAILY_BUDGET_USD: float = 5.0

    # --- Orchestrator budget (Section 3.2) ---
    MAX_TURNS: int = 3
    MAX_TOOL_CALLS: int = 6
    JOB_TIME_BUDGET_SECONDS: float = 45.0
    CONFIDENCE_THRESHOLD: float = 0.5

    # --- Knowledge base ---
    DATA_DIR: Path = ROOT_DIR / "data"
    CHROMA_DIR: Path = ROOT_DIR / "data" / "chroma"
    SQLITE_PATH: Path = ROOT_DIR / "data" / "autodiagnose.db"
    # Minimum cosine similarity for a knowledge-base match to count as grounded evidence.
    RELEVANCE_THRESHOLD: float = 0.40
    SEARCH_TOP_K: int = 5

    # --- API ---
    CORS_ORIGINS: str = "http://localhost:5173"
    MAX_PHOTOS: int = 4
    MAX_PHOTO_BYTES: int = 15 * 1024 * 1024
    NHTSA_ENABLED: bool = True
    # Per-client limit on new diagnoses, protecting the Bedrock budget on a public URL.
    RATE_LIMIT_PER_MINUTE: int = 12

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def has_aws_credentials(self) -> bool:
        return bool(self.AWS_BEARER_TOKEN_BEDROCK or (self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
