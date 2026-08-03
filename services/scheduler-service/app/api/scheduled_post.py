import uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.content_client import get_content
from app.db import get_db
from app.dependencies import get_current_payload, require_publish_role
from app.models.scheduled_post import ScheduledPost, ScheduleStatus
from app.recurrence import compute_next_occurrence, series_root_id
from app.schemas.scheduled_post import RescheduleRequest, ScheduleCreate, ScheduledPostResponse

router = APIRouter()


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": {}}}


def _get_owned(db: Session, schedule_id: str, account_id: str) -> ScheduledPost:
    row = db.query(ScheduledPost).filter(ScheduledPost.id == schedule_id).one_or_none()
    if row is None or row.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_error("schedule_not_found", "No such schedule for this account."))
    return row


def _spawn_next_occurrence(db: Session, row: ScheduledPost) -> None:
    """Inserts the next pending occurrence, if the rule allows one.
    Called both when a row FIRES and when a single occurrence is
    CANCELLED (scope=single) -- cancelling one occurrence must not kill
    the rest of the series. Always stamps the series ROOT id, not the
    immediate predecessor's -- see app/recurrence.py:series_root_id."""
    if not row.recurrence_rule:
        return
    next_at = compute_next_occurrence(row.publish_at, row.recurrence_rule)
    if next_at is None:
        return
    db.add(ScheduledPost(
        id=str(uuid.uuid4()), account_id=row.account_id, content_id=row.content_id,
        has_image=row.has_image, publish_at=next_at, status=ScheduleStatus.PENDING,
        recurrence_rule=row.recurrence_rule, recurrence_parent_id=series_root_id(row),
    ))


@router.get("/calendar", response_model=list[ScheduledPostResponse])
def calendar(
    from_: datetime = Query(..., alias="from"),
    to: datetime = Query(...),
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    rows = db.query(ScheduledPost).filter(
        ScheduledPost.account_id == payload["account_id"],
        ScheduledPost.publish_at >= from_,
        ScheduledPost.publish_at < to,
    ).order_by(ScheduledPost.publish_at).all()
    return rows

from typing import Optional

@router.get("/by-content/{content_id}", response_model=Optional[ScheduledPostResponse])
def by_content(content_id: str, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    """Powers a 'Scheduled for ...' badge on the Content Studio page --
    the next still-PENDING occurrence for this content item, if any."""
    return db.query(ScheduledPost).filter(
        ScheduledPost.account_id == payload["account_id"],
        ScheduledPost.content_id == content_id,
        ScheduledPost.status == ScheduleStatus.PENDING,
    ).order_by(ScheduledPost.publish_at).first()

@router.post("", response_model=ScheduledPostResponse, status_code=status.HTTP_201_CREATED)
async def schedule(
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
    authorization: str | None = Header(default=None),
):
    require_publish_role(payload)

    try:
        content = await get_content(body.content_id, authorization)
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_error("content_service_unavailable", "Could not verify content right now."))
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_error("content_not_found", "No such content for this account."))
    if content["status"] != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_error("content_not_approved", "Only approved content can be scheduled."))

    row = ScheduledPost(
        id=str(uuid.uuid4()), account_id=payload["account_id"], content_id=body.content_id,
        has_image=bool(content.get("image_url")), publish_at=body.publish_at,
        status=ScheduleStatus.PENDING,
        recurrence_rule=body.recurrence_rule.model_dump() if body.recurrence_rule else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{schedule_id}/reschedule", response_model=ScheduledPostResponse)
def reschedule(schedule_id: str, body: RescheduleRequest, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    """Always affects this ONE occurrence only, series or not -- matches
    Google Calendar; see Phase 10 plan."""
    require_publish_role(payload)
    row = _get_owned(db, schedule_id, payload["account_id"])
    if row.status != ScheduleStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_error("schedule_not_pending", f"Schedule is '{row.status.value}', not pending."))
    row.publish_at = body.publish_at
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel(schedule_id: str, scope: str = Query(default="single", pattern="^(single|series)$"),
           db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    require_publish_role(payload)
    row = _get_owned(db, schedule_id, payload["account_id"])
    if row.status != ScheduleStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_error("schedule_not_pending", f"Schedule is '{row.status.value}', not pending."))

    if scope == "series":
        root_id = series_root_id(row)
        db.query(ScheduledPost).filter(
            ScheduledPost.account_id == payload["account_id"],
            ScheduledPost.status == ScheduleStatus.PENDING,
            (ScheduledPost.id == root_id) | (ScheduledPost.recurrence_parent_id == root_id),
        ).update({"status": ScheduleStatus.CANCELLED}, synchronize_session=False)
    else:
        _spawn_next_occurrence(db, row)  # keep the series alive past this one cancelled occurrence
        row.status = ScheduleStatus.CANCELLED

    db.commit()
