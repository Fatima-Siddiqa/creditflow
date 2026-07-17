import secrets

from app.models import PasswordResetToken
from app.schemas import ForgotPasswordRequest, ResetPasswordRequest, IssueScopedTokenRequest, ScopedTokenResponse
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import check_login_rate_limit, register_failed_login, clear_login_attempts, get_current_user, verify_internal_service_secret
from app.events import publish_event
from app.models import User, Credential, EmailVerificationToken, RefreshToken
from app.redis_client import redis_client
from app.schemas import (
    SignupRequest, SignupResponse, VerifyEmailRequest, MessageResponse,
    LoginRequest, TokenPairResponse, RefreshRequest, LogoutRequest,
)
from app.security import hash_password, verify_password, generate_raw_token, hash_token, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_VERIFICATION_TTL_HOURS = 24
REFRESH_TOKEN_TTL_DAYS = 7  # matches settings.refresh_token_ttl_days, kept explicit here for the raw SQL-adjacent logic below
PASSWORD_RESET_TTL_MINUTES = 15

def _generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))

def _issue_token_pair(db: Session, user: User, rotated_from_id=None) -> TokenPairResponse:
    access_token, jti = create_access_token(user_id=user.id, account_id=None, role=None)
    redis_client.setex(f"jti:{jti}", settings.access_token_ttl_minutes * 60, "1")

    raw_refresh = generate_raw_token()
    refresh_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days),
        rotated_from=rotated_from_id,
    )
    db.add(refresh_row)
    db.commit()

    return TokenPairResponse(access_token=access_token, refresh_token=raw_refresh)


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
    print(f"[DEV] Email verification token for {body.email}: {raw_token}")  # TODO: remove once notification-service sends this via email (Phase 13)
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

@router.post("/login", response_model=TokenPairResponse)
async def login(body: LoginRequest, db: Session = Depends(get_db)):
    check_login_rate_limit(body.email)

    user = db.query(User).filter(User.email == body.email).first()
    credential = db.query(Credential).filter(Credential.user_id == user.id).first() if user else None

    if not user or not credential or not verify_password(body.password, credential.password_hash):
        if user:
            register_failed_login(body.email)
        raise _error("invalid_credentials", "Email or password is incorrect.", status.HTTP_401_UNAUTHORIZED)

    if not user.is_verified:
        raise _error("email_not_verified", "Please verify your email before logging in.", status.HTTP_403_FORBIDDEN)

    clear_login_attempts(body.email)
    tokens = _issue_token_pair(db, user)

    await publish_event("user.logged_in", payload={"user_id": str(user.id)})

    return tokens


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(body.refresh_token)
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if not record:
        raise _error("invalid_refresh_token", "Refresh token is invalid.", status.HTTP_401_UNAUTHORIZED)
    if record.revoked:
        # Reuse of an already-rotated (or logged-out) token — treat as a
        # possible token theft, not just an expired-token situation.
        raise _error("refresh_token_reused", "This refresh token has already been used.", status.HTTP_401_UNAUTHORIZED)
    if record.expires_at < datetime.now(timezone.utc):
        raise _error("refresh_token_expired", "Refresh token has expired.", status.HTTP_401_UNAUTHORIZED)

    record.revoked = True
    user = db.query(User).filter(User.id == record.user_id).first()
    tokens = _issue_token_pair(db, user, rotated_from_id=record.id)

    return tokens


@router.post("/logout", response_model=MessageResponse)
def logout(body: LogoutRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    token_hash = hash_token(body.refresh_token)
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if record:
        record.revoked = True
        db.commit()

    redis_client.delete(f"jti:{current_user['jti']}")

    return MessageResponse(message="Logged out successfully.")

@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()

    # Deliberately return the same success message whether or not the email
    # exists — otherwise this endpoint becomes a way to check which emails
    # are registered (a real, if minor, information leak).
    if not user:
        return MessageResponse(message="If that email is registered, a reset code has been sent.")

    otp = _generate_otp()
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES),
    )
    db.add(reset_token)
    db.commit()

    # Same caveat as signup: notification-service (Phase 13) doesn't exist
    # yet, so this otp only reaches you via the event payload / DB for now.
    await publish_event(
        "user.password_reset_requested",
        payload={"user_id": str(user.id), "email": user.email, "otp": otp},
    )

    return MessageResponse(message="If that email is registered, a reset code has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(body.token)
    record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash
    ).first()

    if not record:
        raise _error("invalid_token", "Reset code is invalid.", status.HTTP_400_BAD_REQUEST)
    if record.used:
        raise _error("token_already_used", "Reset code has already been used.", status.HTTP_400_BAD_REQUEST)
    if record.expires_at < datetime.now(timezone.utc):
        raise _error("token_expired", "Reset code has expired.", status.HTTP_400_BAD_REQUEST)

    credential = db.query(Credential).filter(Credential.user_id == record.user_id).first()
    credential.password_hash = hash_password(body.new_password)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == record.user_id, RefreshToken.revoked == False
    ).update({"revoked": True})
    record.used = True
    db.commit()

    return MessageResponse(message="Password reset successfully.")

@router.post(
    "/issue-scoped-token",
    response_model=ScopedTokenResponse,
    dependencies=[Depends(verify_internal_service_secret)],
)
def issue_scoped_token(body: IssueScopedTokenRequest, db: Session = Depends(get_db)):
    """Internal, service-to-service only (see verify_internal_service_secret).
    Called by User/Tenant Service (Phase 4) after IT has already verified
    the user belongs to account_id with this role — this service does not
    re-check membership itself, since it owns identity, not accounts.

    Mints a fresh account-scoped access token only. Does not rotate or
    revoke the user's existing refresh token, and does not touch any other
    account's jti — a user can hold concurrently-valid scoped tokens for
    several accounts at once (e.g. two browser tabs on two workspaces).
    """
    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise _error("user_not_found", "User does not exist.", status.HTTP_404_NOT_FOUND)
    if not user.is_verified:
        raise _error("email_not_verified", "User's email is not verified.", status.HTTP_403_FORBIDDEN)

    access_token, jti = create_access_token(user_id=user.id, account_id=body.account_id, role=body.role)
    redis_client.setex(f"jti:{jti}", settings.access_token_ttl_minutes * 60, "1")

    return ScopedTokenResponse(access_token=access_token)