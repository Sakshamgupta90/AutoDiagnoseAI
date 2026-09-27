from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    USD_BUDGET_CAP: float = 10.0
    MAX_TOKENS: int = 4096

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
