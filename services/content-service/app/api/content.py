import uuid
import os
from fastapi import UploadFile, File
from app.config import settings
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_payload, require_publish_role, verify_internal_service_secret
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


@router.post("/{content_id}/image", response_model=ContentResponse)
async def upload_content_image(content_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    content = _get_owned_content(db, content_id, payload["account_id"])
    content_dir = os.path.join(settings.upload_dir, content_id)
    os.makedirs(content_dir, exist_ok=True)
    file_path = os.path.join(content_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    content.image_url = file_path
    content.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(content)

    await publish_event("content.updated", {"content_id": content_id, "account_id": content.account_id}, account_id=content.account_id)
    return _to_response(db, content)


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

@router.post("/{content_id}/image", response_model=ContentResponse)
async def upload_content_image(
    content_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Spec §8 Service 8: "Manual image upload endpoint (multipart) for
    cases where the user supplies their own image instead of generating
    one." Writes to settings.upload_dir (a local volume in dev/docker-
    compose; swap for S3 in the AWS bonus) and stores a servable path on
    Content.image_url -- this is the *current* image for the content
    item as a whole, distinct from a ContentVersion's own image_url
    (which records whatever image, if any, was attached back when that
    particular version was generated).

    Stored under a per-content-id subfolder (upload_dir/{content_id}/{original_filename})
    rather than renaming to content_id.ext: keeping the original filename
    in image_url is part of this endpoint's contract (see
    tests/test_image_upload.py's `.endswith("test.jpg")` assertion) --
    the subfolder is what prevents two different content items that
    happen to upload same-named files from colliding, since the
    filename itself is no longer unique on its own.
    """
    content = _get_owned_content(db, content_id, payload["account_id"])

    safe_filename = os.path.basename(file.filename or "upload.bin")
    content_dir = os.path.join(settings.upload_dir, content_id)
    os.makedirs(content_dir, exist_ok=True)
    stored_path = os.path.join(content_dir, safe_filename)

    file_bytes = await file.read()
    with open(stored_path, "wb") as f:
        f.write(file_bytes)

    content.image_url = f"/uploads/{content_id}/{safe_filename}"
    content.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(content)

    await publish_event(
        "content.updated",
        {"content_id": content_id, "account_id": content.account_id, "status": content.status.value},
        account_id=content.account_id,
    )
    return _to_response(db, content)

@router.get("/{content_id}/internal", dependencies=[Depends(verify_internal_service_secret)])
def get_content_internal(content_id: str, db: Session = Depends(get_db)):
    content = db.query(Content).filter(Content.id == content_id).one_or_none()
    if content is None:
        raise HTTPException(status_code=404, detail=_error("content_not_found", "No such content."))
    return {"content_id": content.id, "account_id": content.account_id, "body": _latest_body(db, content), "image_url": content.image_url}