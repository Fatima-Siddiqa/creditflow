from sqlalchemy import Column, DateTime, String, func

from app.db import Base


class ProcessedEvent(Base):
    """Keyed on Stripe's OWN event id (payload['stripe_event_id']), not
    our envelope's event_id — see webhooks.py's comment in api-gateway.
    Stripe's id is the stable, meaningful dedup key here; our envelope's
    uuid4 only protects against RabbitMQ-level redelivery, not against
    Gateway's 24h dedup window expiring and Stripe genuinely retrying an
    old delivery under a fresh envelope."""
    __tablename__ = "processed_events"

    stripe_event_id = Column(String, primary_key=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())