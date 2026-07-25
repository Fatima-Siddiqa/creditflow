import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.redis_client import redis_client
from app.config import settings

_robots_cache: dict[str, RobotFileParser] = {}


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def is_allowed(url: str, user_agent: str = "CreditFlowScraperBot") -> bool:
    """Fetches and checks robots.txt for the target's origin. Fails open
    (allowed) only if robots.txt itself is unreachable/404 -- that's
    standard robots.txt semantics, not a scraper bug."""
    origin = _origin(url)
    rp = _robots_cache.get(origin)
    if rp is None:
        rp = RobotFileParser()
        rp.set_url(f"{origin}/robots.txt")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{origin}/robots.txt")
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp.parse([])
        except httpx.HTTPError:
            rp.parse([])
        _robots_cache[origin] = rp
    return rp.can_fetch(user_agent, url)


def enforce_domain_rate_limit(url: str) -> None:
    """Blocking sleep (called from a worker/background task, not a request
    handler) so two requests to the same domain in quick succession are
    spaced out rather than fired concurrently."""
    domain = urlparse(url).netloc
    key = f"scraper:last_fetch:{domain}"
    last = redis_client.get(key)
    now = time.monotonic()
    if last is not None:
        elapsed = now - float(last)
        wait = settings.domain_rate_limit_seconds - elapsed
        if wait > 0:
            time.sleep(wait)
    redis_client.set(key, time.monotonic(), ex=settings.domain_rate_limit_seconds * 10)