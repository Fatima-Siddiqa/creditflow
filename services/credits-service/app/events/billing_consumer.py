import json
import uuid
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models.ledger import CreditLedger, ProcessedEvent, TransactionType
from app.events.publisher import publish_event

def process_billing_event(ch, method, properties, body):
    event = json.loads(body)
    event_id = event.get("event_id")
    event_type = event.get("type")
    
    db: Session = SessionLocal()
    try:
        # Idempotency check
        if db.query(ProcessedEvent).filter_by(event_id=event_id).first():
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        if event_type == "invoice.paid":
            # Map plan to credit amount (simplified for example)
            credits_to_add = 1000 if event["data"]["plan"] == "Pro" else 100
            entry = CreditLedger(
                id=str(uuid.uuid4()),
                account_id=event["data"]["account_id"],
                amount=credits_to_add,
                transaction_type=TransactionType.PURCHASE,
                reference_id=event["data"]["invoice_id"]
            )
            db.add(entry)
            
            publish_event("credits.credited", {
                "account_id": event["data"]["account_id"],
                "amount": credits_to_add
            })

        elif event_type == "refund.issued":
             # Clawback logic
             entry = CreditLedger(
                id=str(uuid.uuid4()),
                account_id=event["data"]["account_id"],
                amount=-event["data"]["refunded_credits"],
                transaction_type=TransactionType.REFUND_CLAWBACK,
                reference_id=event["data"]["refund_id"]
            )
             db.add(entry)

        # Mark event as processed
        db.add(ProcessedEvent(event_id=event_id))
        db.commit()
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        db.rollback()
        # Nack to requeue or DLQ
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    finally:
        db.close()