import asyncio, httpx
from datetime import datetime, timedelta, timezone
from app.config import settings
from app.crypto import decrypt, encrypt
from app.db import SessionLocal
from app.models.social import SocialConnection

REFRESH_URL = "https://www.linkedin.com/oauth/v2/accessToken"
CHECK_INTERVAL_SECONDS = 3600
REFRESH_BUFFER = timedelta(days=1)


async def refresh_expiring_tokens() -> None:
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) + REFRESH_BUFFER
        due = db.query(SocialConnection).filter(SocialConnection.expires_at <= cutoff).all()
        for conn in due:
            if conn.refresh_token_enc is None:
                continue
            async with httpx.AsyncClient() as client:
                resp = await client.post(REFRESH_URL, data={
                    "grant_type": "refresh_token", "refresh_token": decrypt(conn.refresh_token_enc),
                    "client_id": settings.linkedin_client_id, "client_secret": settings.linkedin_client_secret,
                })
                resp.raise_for_status()
                tokens = resp.json()
            conn.access_token_enc = encrypt(tokens["access_token"])
            conn.expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
        db.commit()
    finally:
        db.close()


async def run_token_refresh_loop() -> None:
    while True:
        await refresh_expiring_tokens()
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)