import json
from typing import AsyncGenerator

import httpx

from app.config import settings


class OpenRouterError(Exception):
    """Raised for both transport failures (timeout, connection refused,
    non-200 response) and in-stream errors OpenRouter reports. The
    message becomes the `[ERROR] <reason>` sentinel published to
    `sse:<job_id>` (see app/sse_publisher.py and app/generation_worker.py),
    so keep it short and user-facing rather than a raw traceback."""

async def stream_chat_completion(models: list[str], prompt: str) -> AsyncGenerator[str, None]:
    last_error: OpenRouterError | None = None
    for model in models:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)) as client:
                async with client.stream("POST", f"{settings.openrouter_base_url}/chat/completions",
                                          json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": True},
                                          headers={"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json"}) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        last_error = OpenRouterError(f"{model} returned {response.status_code}: {body.decode(errors='replace')[:200]}")
                        continue  # try the next candidate
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line.removeprefix("data: ").strip()
                        if data == "[DONE]":
                            return
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        content = choices[0].get("delta", {}).get("content")
                        if content:
                            yield content
                    return
        except httpx.HTTPError as exc:
            last_error = OpenRouterError(f"{model} request failed: {exc}")
            continue
    raise last_error or OpenRouterError("No fallback models available.")