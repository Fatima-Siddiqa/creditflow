"""
Scraping engine choice: httpx + simple HTML text/meta extraction, not a
full headless browser (Playwright/Crawl4AI). Documented tradeoff: the spec
names Crawl4AI/Playwright as options, but both need a browser binary baked
into the image, which is heavy for a bonus service. httpx-based extraction
covers static/server-rendered pages (blogs, competitor landing pages,
"trend" pages) which is what a content-generation feed realistically needs.
If a target requires JS rendering, swap httpx.get for Crawl4AI's
AsyncWebCrawler here -- the rest of the pipeline (robots check, rate limit,
Mongo storage, event emission) is unchanged either way.
"""
import re
from datetime import datetime, timezone

import httpx

from app.robots import is_allowed, enforce_domain_rate_limit


class ScrapeBlocked(Exception):
    """Raised when robots.txt disallows the target."""


class ScrapeFailed(Exception):
    """Raised on network/HTTP failure."""


def _extract(html: str) -> dict:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else None
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return {"title": title, "text_excerpt": text[:5000]}


async def run_scrape(target_url: str, job_type: str) -> dict:
    """Returns the `data` payload to store. Raises ScrapeBlocked/ScrapeFailed."""
    if not await is_allowed(target_url):
        raise ScrapeBlocked(f"robots.txt disallows {target_url}")

    enforce_domain_rate_limit(target_url)

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(target_url, headers={"User-Agent": "CreditFlowScraperBot"})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ScrapeFailed(str(exc)) from exc

    extracted = _extract(resp.text)
    return {"job_type": job_type, "status_code": resp.status_code, **extracted,
            "extracted_at": datetime.now(timezone.utc).isoformat()}