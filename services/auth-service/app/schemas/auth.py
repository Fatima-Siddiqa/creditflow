import uuid

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class SignupResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    is_verified: bool


class VerifyEmailRequest(BaseModel):
    token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class MessageResponse(BaseModel):
    message: str

class IssueScopedTokenRequest(BaseModel):
    """Called internally by User/Tenant Service (Phase 4) after it has
    already verified the user belongs to account_id with this role — this
    service does not re-check membership, it only trusts the caller (see
    verify_internal_service_secret) and mints the token."""
    user_id: uuid.UUID
    account_id: uuid.UUID
    role: str


class ScopedTokenResponse(BaseModel):
    """Deliberately no refresh_token here — account-switching re-scopes the
    access token only; the user's existing refresh token (issued at login,
    account-agnostic) keeps working for renewing the session regardless of
    which account is currently active."""
    access_token: str
    token_type: str = "bearer"

class UserEmailResponse(BaseModel):
    """Internal-only lookup (Phase 13 addition) so other services can
    resolve a recipient's email from a bare user_id -- most domain events
    (member.joined, usage.threshold_reached, post.published, etc.) carry
    user_id/account_id, not email, since auth-service is the only service
    that owns email addresses."""
    user_id: uuid.UUID
    email: str