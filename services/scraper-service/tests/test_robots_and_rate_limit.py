import time

import httpx
import pytest

from app import robots


class _FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)


class _FakeAsyncClient:
    def __init__(self, robots_txt, **kwargs):
        self._robots_txt = robots_txt
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, url, **kwargs):
        return _FakeResponse(200, self._robots_txt)


@pytest.mark.asyncio
async def test_robots_disallow_blocks_scrape(monkeypatch):
    robots._robots_cache.clear()
    disallow_txt = "User-agent: *\nDisallow: /blocked"

    def fake_client_factory(**kwargs):
        return _FakeAsyncClient(disallow_txt, **kwargs)

    monkeypatch.setattr(robots.httpx, "AsyncClient", fake_client_factory)
    allowed = await robots.is_allowed("https://example.com/blocked/page")
    assert allowed is False


@pytest.mark.asyncio
async def test_robots_allow_permits_scrape(monkeypatch):
    robots._robots_cache.clear()
    allow_txt = "User-agent: *\nAllow: /"

    def fake_client_factory(**kwargs):
        return _FakeAsyncClient(allow_txt, **kwargs)

    monkeypatch.setattr(robots.httpx, "AsyncClient", fake_client_factory)
    allowed = await robots.is_allowed("https://example.com/open/page")
    assert allowed is True


def test_rate_limit_spaces_out_same_domain_requests(monkeypatch, redis_conn):
    monkeypatch.setattr(robots.settings, "domain_rate_limit_seconds", 1)
    monkeypatch.setattr(robots, "redis_client", redis_conn)

    start = time.monotonic()
    robots.enforce_domain_rate_limit("https://ratelimited.com/a")
    robots.enforce_domain_rate_limit("https://ratelimited.com/b")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.9