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


async def stream_chat_completion(model: str, prompt: str) -> AsyncGenerator[str, None]:
    """Wraps OpenRouter's OpenAI-compatible streaming chat completions
    endpoint (spec §8 Service 7: "Call OpenRouter's streaming completion
    endpoint"). Yields plain-text token chunks as they arrive -- no JSON
    wrapping -- matching the sse:<job_id> contract the Gateway already
    expects (api-gateway/app/api/sse.py: raw text = a token chunk).

    OpenRouter's stream is standard SSE: lines prefixed `data: `, each a
    JSON chunk shaped like OpenAI's `choices[0].delta.content`,
    terminated by the literal line `data: [DONE]`. This does NOT
    re-publish OpenRouter's own [DONE] onto sse:<job_id> -- the caller
    (app/generation_worker.py) decides when to publish this service's
    own [DONE], since PR #4 will insert a persistence step in between
    "OpenRouter finished" and "tell the frontend we're done".
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        ) as client:
            async with client.stream(
                "POST",
                f"{settings.openrouter_base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise OpenRouterError(
                        f"OpenRouter returned {response.status_code}: "
                        f"{body.decode(errors='replace')[:200]}"
                    )

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ").strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue  # keep-alive comment lines etc. -- not our concern
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    content = choices[0].get("delta", {}).get("content")
                    if content:
                        yield content
    except httpx.HTTPError as exc:
        raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc