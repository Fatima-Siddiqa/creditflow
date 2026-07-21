import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_payload, require_publish_role
from app.events.publisher import publish_event
from app.models.content import Content, ContentStatus, ContentVersion
from app.schemas.content import ContentCreate, ContentResponse, ContentUpdate

router = APIRouter()


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": {}}}


def _get_owned_content(db: Session, content_id: str, account_id: str) -> Content:
    """404 (not 403) on cross-account access or missing id — same
    can't-probe-other-accounts rationale as ai-generation-service's
    cancel endpoint."""
    content = db.query(Content).filter(Content.id == content_id).one_or_none()
    if content is None or content.account_id != account_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_error("content_not_found", "No such content for this account."))
    return content


def _latest_body(db: Session, content: Content) -> str:
    version = db.query(ContentVersion).filter(ContentVersion.id == content.current_version_id).one_or_none()
    return version.body if version else ""


def _to_response(db: Session, content: Content) -> ContentResponse:
    return ContentResponse(
        id=content.id, account_id=content.account_id, created_by_user_id=content.created_by_user_id,
        status=content.status.value, image_url=content.image_url, current_version_id=content.current_version_id,
        body=_latest_body(db, content), created_at=content.created_at, updated_at=content.updated_at,
    )


@router.post("", response_model=ContentResponse, status_code=status.HTTP_201_CREATED)
async def create_content(body: ContentCreate, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    account_id, user_id = payload["account_id"], payload["sub"]
    content_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())

    content = Content(id=content_id, account_id=account_id, created_by_user_id=user_id, status=ContentStatus.DRAFT,
                       image_url=body.image_url, current_version_id=version_id)
    db.add(content)
    db.add(ContentVersion(id=version_id, content_id=content_id, body=body.body, image_url=body.image_url, created_by_user_id=user_id))
    db.commit()
    db.refresh(content)

    await publish_event("content.created", {"content_id": content_id, "account_id": account_id, "status": "draft"}, account_id=account_id)
    return _to_response(db, content)


@router.get("", response_model=list[ContentResponse])
def list_content(db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    rows = db.query(Content).filter(Content.account_id == payload["account_id"]).order_by(Content.created_at.desc()).all()
    return [_to_response(db, c) for c in rows]


@router.get("/{content_id}", response_model=ContentResponse)
def get_content(content_id: str, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    content = _get_owned_content(db, content_id, payload["account_id"])
    return _to_response(db, content)


@router.patch("/{content_id}", response_model=ContentResponse)
async def update_content(content_id: str, body: ContentUpdate, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    """Creates a new ContentVersion row -- never overwrites the old one.
    Does NOT touch status: editing an approved/published item leaving
    status as-is is a literal reading of Phase 9's test list (only
    version-creation is asserted); revisit if product wants edits to
    revert status to draft for re-approval."""
    content = _get_owned_content(db, content_id, payload["account_id"])
    version_id = str(uuid.uuid4())
    db.add(ContentVersion(id=version_id, content_id=content_id, body=body.body, image_url=body.image_url, created_by_user_id=payload["sub"]))
    content.current_version_id = version_id
    content.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(content)

    await publish_event("content.updated", {"content_id": content_id, "account_id": content.account_id}, account_id=content.account_id)
    return _to_response(db, content)


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content(content_id: str, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    content = _get_owned_content(db, content_id, payload["account_id"])
    db.query(ContentVersion).filter(ContentVersion.content_id == content_id).delete()
    db.delete(content)
    db.commit()


@router.post("/{content_id}/approve", response_model=ContentResponse)
async def approve_content(content_id: str, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    require_publish_role(payload)
    content = _get_owned_content(db, content_id, payload["account_id"])
    if content.status != ContentStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_error("invalid_transition", f"Cannot approve from status '{content.status.value}'."))
    content.status = ContentStatus.APPROVED
    content.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(content)

    await publish_event("content.updated", {"content_id": content_id, "account_id": content.account_id, "status": "approved"}, account_id=content.account_id)
    return _to_response(db, content)


@router.post("/{content_id}/publish-request", response_model=ContentResponse)
async def publish_request_content(content_id: str, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    """Only gates the status machine -- the actual LinkedIn publish
    happens in Scheduler -> Social Publishing (Phase 10/11), per spec."""
    require_publish_role(payload)
    content = _get_owned_content(db, content_id, payload["account_id"])
    if content.status != ContentStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_error("invalid_transition", f"Cannot publish-request from status '{content.status.value}'."))
    content.status = ContentStatus.PUBLISHED
    content.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(content)

    await publish_event("content.updated", {"content_id": content_id, "account_id": content.account_id, "status": "published"}, account_id=content.account_id)
    return _to_response(db, content)