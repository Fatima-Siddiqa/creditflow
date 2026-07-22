import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.events.publish_consumer import apply_content_scheduled
from app.crypto import encrypt
from app.models.social import SocialConnection, PublishJob, PublishStatus, PostMedia


def _connect(db, account_id="acc_123"):
    db.add(SocialConnection(account_id=account_id, linkedin_member_urn="urn:li:person:abc",
                             access_token_enc=encrypt("fake-token"), expires_at="2099-01-01"))
    db.flush()


def _event(account_id="acc_123", content_id="content_1", schedule_id=None):
    return {"event_id": str(uuid.uuid4()), "event_type": "content.scheduled",
            "payload": {"account_id": account_id, "content_id": content_id, "schedule_id": schedule_id or str(uuid.uuid4())}}


@pytest.mark.asyncio
async def test_no_connection_is_a_noop(db_session):
    applied = await apply_content_scheduled(db_session, _event())
    assert applied is False


@pytest.mark.asyncio
async def test_text_only_path_no_image_calls(db_session):
    _connect(db_session)
    fake_content = {"body": "hello", "image_url": None}

    with patch("app.events.publish_consumer.httpx.AsyncClient") as MockClient, \
         patch("app.events.publish_consumer.register_upload", new=AsyncMock()) as mock_register, \
         patch("app.events.publish_consumer.upload_binary", new=AsyncMock()) as mock_upload, \
         patch("app.events.publish_consumer.publish_ugc_post", new=AsyncMock(return_value="urn:li:share:999")) as mock_post:

        mock_resp = AsyncMock()
        mock_resp.json = lambda: fake_content
        mock_resp.raise_for_status = lambda: None
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        applied = await apply_content_scheduled(db_session, _event())

    assert applied is True
    mock_register.assert_not_called()
    mock_upload.assert_not_called()
    mock_post.assert_called_once_with("fake-token", "urn:li:person:abc", "hello", None)

    job = db_session.query(PublishJob).filter(PublishJob.account_id == "acc_123").one()
    assert job.status == PublishStatus.PUBLISHED
    assert job.linkedin_post_urn == "urn:li:share:999"


@pytest.mark.asyncio
async def test_image_path_registers_uploads_and_references_asset_urn(db_session):
    """The single most important test in this phase, per the phase doc:
    confirms the 3-step LinkedIn Images flow runs and the resulting
    asset URN is the one actually passed into the UGC post -- not a
    text-only fallback."""
    _connect(db_session)
    fake_content = {"body": "hello with image", "image_url": "http://content-service/uploads/x.jpg"}

    with patch("app.events.publish_consumer.httpx.AsyncClient") as MockClient, \
         patch("app.events.publish_consumer.register_upload", new=AsyncMock(return_value=("http://upload-url", "urn:li:digitalmediaAsset:abc123"))) as mock_register, \
         patch("app.events.publish_consumer.upload_binary", new=AsyncMock()) as mock_upload, \
         patch("app.events.publish_consumer.publish_ugc_post", new=AsyncMock(return_value="urn:li:share:111")) as mock_post:

        content_resp = AsyncMock()
        content_resp.json = lambda: fake_content
        content_resp.raise_for_status = lambda: None
        image_resp = AsyncMock()
        image_resp.content = b"fake-image-bytes"

        MockClient.return_value.__aenter__.return_value.get = AsyncMock(side_effect=[content_resp, image_resp])

        applied = await apply_content_scheduled(db_session, _event())

    assert applied is True
    mock_register.assert_called_once_with("fake-token", "urn:li:person:abc")
    mock_upload.assert_called_once_with("http://upload-url", "fake-token", b"fake-image-bytes")
    mock_post.assert_called_once_with("fake-token", "urn:li:person:abc", "hello with image", "urn:li:digitalmediaAsset:abc123")

    media = db_session.query(PostMedia).one()
    assert media.linkedin_asset_urn == "urn:li:digitalmediaAsset:abc123"


@pytest.mark.asyncio
async def test_redelivered_event_for_already_published_job_does_not_post_twice(db_session):
    """apply_content_scheduled itself has no idempotency check -- that
    lives in _handle_event's processed_events insert, one layer up. This
    test exercises that layer via _handle_event directly."""
    from app.events.publish_consumer import _handle_event

    _connect(db_session)
    event = _event()

    with patch("app.events.publish_consumer.httpx.AsyncClient") as MockClient, \
         patch("app.events.publish_consumer.register_upload", new=AsyncMock()), \
         patch("app.events.publish_consumer.upload_binary", new=AsyncMock()), \
         patch("app.events.publish_consumer.publish_ugc_post", new=AsyncMock(return_value="urn:li:share:222")):

        mock_resp = AsyncMock()
        mock_resp.json = lambda: {"body": "hi", "image_url": None}
        mock_resp.raise_for_status = lambda: None
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        first_applied, _ = await _handle_event(event)
        second_applied, _ = await _handle_event(event)  # same event_id, redelivered

    assert first_applied is True
    assert second_applied is False
    assert db_session.query(PublishJob).filter(PublishJob.account_id == "acc_123").count() == 1