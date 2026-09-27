"""Claude on Amazon Bedrock via the Anthropic SDK, with cost controls (Section 7.3).

Every failure mode (no credentials, network, throttling, daily budget reached)
surfaces as `LLMUnavailable`, which the orchestrator turns into the local
knowledge-base fallback and the "Cloud unreachable" notice.
"""

import logging
from dataclasses import dataclass
from typing import Any

import anthropic
from anthropic import AsyncAnthropicBedrock

from src.core.config import settings
from src.storage import db

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    def __init__(self, reason: str, *, budget: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.budget = budget


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, tokens_in: int, tokens_out: int) -> float:
        cost = (tokens_in * settings.PRICE_INPUT_PER_MTOK + tokens_out * settings.PRICE_OUTPUT_PER_MTOK) / 1_000_000
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.cost_usd += cost
        self.calls += 1
        return cost


class ClaudeClient:
    def __init__(self) -> None:
        self._client: AsyncAnthropicBedrock | None = None
        self.model = settings.BEDROCK_MODEL_ID

    @property
    def enabled(self) -> bool:
        return settings.LLM_ENABLED

    def _get_client(self) -> AsyncAnthropicBedrock:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "aws_region": settings.AWS_REGION,
                "timeout": settings.LLM_TIMEOUT_SECONDS,
                "max_retries": 2,
            }
            if settings.AWS_BEARER_TOKEN_BEDROCK:
                kwargs["api_key"] = settings.AWS_BEARER_TOKEN_BEDROCK
            elif settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                kwargs.update(
                    aws_access_key=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_key=settings.AWS_SECRET_ACCESS_KEY,
                    aws_session_token=settings.AWS_SESSION_TOKEN or None,
                )
            # Otherwise the SDK falls back to the default AWS credential chain (~/.aws, instance role).
            self._client = AsyncAnthropicBedrock(**kwargs)
        return self._client

    async def create(self, usage: Usage, **kwargs: Any) -> Any:
        """One Messages API call. Raises LLMUnavailable instead of provider-specific errors."""
        if not self.enabled:
            raise LLMUnavailable("AI model disabled (LLM_ENABLED=false).")
        spent = db.spend_today()["cost_usd"]
        if spent >= settings.DAILY_BUDGET_USD:
            raise LLMUnavailable(
                f"Daily AI budget of ${settings.DAILY_BUDGET_USD:.2f} reached (spent ${spent:.2f}).", budget=True
            )
        kwargs.setdefault("max_tokens", settings.LLM_MAX_TOKENS)
        try:
            message = await self._get_client().messages.create(model=self.model, **kwargs)
        except anthropic.CredentialsError as exc:
            raise LLMUnavailable("AWS credentials are not configured for Bedrock.") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise LLMUnavailable("Bedrock rejected the credentials or model access is not enabled.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMUnavailable(f"Bedrock model '{self.model}' not found in {settings.AWS_REGION}.") from exc
        except anthropic.RateLimitError as exc:
            logger.warning("Bedrock throttled: %s", exc.message)
            raise LLMUnavailable(f"Bedrock is throttling requests ({exc.message}).") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMUnavailable("Bedrock timed out.") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable("Can't reach AWS Bedrock.") from exc
        except anthropic.APIStatusError as exc:
            logger.error("Bedrock API error %s: %s", exc.status_code, exc.message)
            raise LLMUnavailable(f"Bedrock error (HTTP {exc.status_code}).") from exc
        except anthropic.AnthropicError as exc:
            logger.exception("Unexpected Anthropic SDK error")
            raise LLMUnavailable("Unexpected error calling Bedrock.") from exc

        tokens_in = message.usage.input_tokens
        tokens_out = message.usage.output_tokens
        cost = usage.add(tokens_in, tokens_out)
        db.record_usage(tokens_in, tokens_out, cost)
        logger.info("Bedrock call: in=%d out=%d cost=$%.4f stop=%s", tokens_in, tokens_out, cost, message.stop_reason)
        return message


claude = ClaudeClient()
