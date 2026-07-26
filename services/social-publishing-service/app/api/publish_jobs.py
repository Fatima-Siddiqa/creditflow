from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_payload
from app.models.social import PublishJob
from app.schemas.publish_job import PublishJobResponse

router = APIRouter()


@router.get("/publish-jobs", response_model=list[PublishJobResponse])
def list_publish_jobs(
    scheduled_post_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    """Spec §4 LinkedIn Connections page: 'last-publish status per post.'
    Scoped unconditionally by account_id from the JWT -- same
    can't-probe-other-accounts posture as every other list endpoint in
    this codebase, since there's no id-based lookup path here that could
    leak a job belonging to a different account.

    Most-recent-first, capped at 50: this is a status feed for "what
    just happened", not a paginated audit log -- Admin Service's
    audit_log (Phase 14) is the right place for full history."""
    query = db.query(PublishJob).filter(PublishJob.account_id == payload["account_id"])
    if scheduled_post_id is not None:
        query = query.filter(PublishJob.scheduled_post_id == scheduled_post_id)
    return query.order_by(PublishJob.created_at.desc()).limit(50).all()