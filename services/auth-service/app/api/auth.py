from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.events import publish_event
from app.models import User, Credential, EmailVerificationToken
from app.schemas import SignupRequest, SignupResponse, VerifyEmailRequest, MessageResponse
from app.security import hash_password, generate_raw_token, hash_token

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_VERIFICATION_TTL_HOURS = 24


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "details": {}}},
    )


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise _error("email_already_registered", "An account with this email already exists.", status.HTTP_409_CONFLICT)

    user = User(email=body.email, is_verified=False)
    db.add(user)
    db.flush()  # assigns user.id without committing yet

    credential = Credential(user_id=user.id, password_hash=hash_password(body.password))
    db.add(credential)

    raw_token = generate_raw_token()
    verification = EmailVerificationToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS),
    )
    db.add(verification)

    db.commit()
    db.refresh(user)

    # See app/events/publisher.py docstring/commit note: direct publish after
    # commit, not outbox — acceptable gap for auth-service per EVENT_CONTRACTS.md.
    # raw_token would normally only reach the user via the email notification-
    # service sends when it consumes this event; notification-service doesn't
    # exist yet (Phase 13), so for now grab it from the DB to test manually.
    await publish_event(
        "user.registered",
        payload={"user_id": str(user.id), "email": user.email, "verification_token": raw_token},
    )

    return SignupResponse(id=user.id, email=user.email, is_verified=user.is_verified)


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(body.token)
    record = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token_hash == token_hash
    ).first()

    if not record:
        raise _error("invalid_token", "Verification token is invalid.", status.HTTP_400_BAD_REQUEST)
    if record.used:
        raise _error("token_already_used", "Verification token has already been used.", status.HTTP_400_BAD_REQUEST)
    if record.expires_at < datetime.now(timezone.utc):
        raise _error("token_expired", "Verification token has expired.", status.HTTP_400_BAD_REQUEST)

    user = db.query(User).filter(User.id == record.user_id).first()
    user.is_verified = True
    record.used = True
    db.commit()

    return MessageResponse(message="Email verified successfully.")