"""Smoke-test the Bedrock connection with one tiny request (costs a fraction of a cent).

Usage: python -m src.llm.check
"""

import asyncio

from src.core.config import settings
from src.llm.claude import LLMUnavailable, Usage, claude
from src.storage import db


async def main() -> None:
    db.connect()
    print(f"Model:  {settings.BEDROCK_MODEL_ID}\nRegion: {settings.AWS_REGION}")
    usage = Usage()
    try:
        msg = await claude.create(usage, max_tokens=20, messages=[{"role": "user", "content": "Reply with just: OK"}])
    except LLMUnavailable as exc:
        print(f"FAILED: {exc.reason}")
        raise SystemExit(1) from exc
    text = "".join(b.text for b in msg.content if b.type == "text")
    print(f"Reply:  {text.strip()}\nTokens: {usage.tokens_in} in / {usage.tokens_out} out (${usage.cost_usd:.5f})\nBedrock connection OK.")


if __name__ == "__main__":
    asyncio.run(main())
