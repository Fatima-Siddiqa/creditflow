import uuid, httpx
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import settings
from app.crypto import encrypt
from app.db import get_db
from app.dependencies import get_current_payload
from app.models.social import SocialConnection

router = APIRouter()
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


@router.get("/linkedin/connect")
def connect(payload: dict = Depends(get_current_payload)):
    params = f"response_type=code&client_id={settings.linkedin_client_id}&redirect_uri={settings.linkedin_redirect_uri}&scope=openid%20profile%20email%20w_member_social&state={payload['account_id']}"
    return RedirectResponse(f"{LINKEDIN_AUTH_URL}?{params}")


@router.get("/linkedin/callback")
async def callback(code: str, state: str, db: Session = Depends(get_db)):
    account_id = state
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(LINKEDIN_TOKEN_URL, data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": settings.linkedin_redirect_uri,
            "client_id": settings.linkedin_client_id, "client_secret": settings.linkedin_client_secret,
        })
        token_resp.raise_for_status()
        tokens = token_resp.json()

        userinfo_resp = await client.get(LINKEDIN_USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        userinfo_resp.raise_for_status()
        member_urn = f"urn:li:person:{userinfo_resp.json()['sub']}"

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
    conn = db.query(SocialConnection).filter(SocialConnection.account_id == account_id).one_or_none()
    if conn is None:
        conn = SocialConnection(account_id=account_id, linkedin_member_urn=member_urn,
                                 access_token_enc=encrypt(tokens["access_token"]),
                                 refresh_token_enc=encrypt(tokens["refresh_token"]) if "refresh_token" in tokens else None,
                                 expires_at=expires_at)
        db.add(conn)
    else:
        conn.linkedin_member_urn = member_urn
        conn.access_token_enc = encrypt(tokens["access_token"])
        if "refresh_token" in tokens:
            conn.refresh_token_enc = encrypt(tokens["refresh_token"])
        conn.expires_at = expires_at
    db.commit()
    return {"status": "connected"}


@router.delete("/linkedin/disconnect")
def disconnect(db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    db.query(SocialConnection).filter(SocialConnection.account_id == payload["account_id"]).delete()
    db.commit()
    return {"status": "disconnected"}


@router.get("/linkedin/status")
def status(db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    conn = db.query(SocialConnection).filter(SocialConnection.account_id == payload["account_id"]).one_or_none()
    return {"connected": conn is not None, "expires_at": conn.expires_at if conn else None}