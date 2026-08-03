import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_payload, require_owner
from app.models import Invoice, OutboxEvent, Subscription
from app.config import settings
from app.schemas import (
    CheckoutSessionRequest, CheckoutSessionResponse, InvoiceResponse,
    PlanChangeRequest, RefundRequest, SubscriptionResponse,
)
from app.stripe_client import create_checkout_session, create_customer, create_refund, update_subscription_plan

router = APIRouter()

VALID_PLANS = {"pro", "team"}


def _get_or_create_subscription(db: Session, account_id: uuid.UUID) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.account_id == account_id).first()
    if sub is None:
        stripe_customer_id = create_customer(account_id)
        sub = Subscription(account_id=account_id, stripe_customer_id=stripe_customer_id, plan_tier="free", status="active")
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


@router.post("/billing/checkout-session", response_model=CheckoutSessionResponse, status_code=status.HTTP_201_CREATED)
def checkout_session(
    body: CheckoutSessionRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    require_owner(payload)
    if body.plan_tier not in VALID_PLANS:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_plan", "message": f"plan_tier must be one of: {', '.join(sorted(VALID_PLANS))}.", "details": {}}})

    account_id = uuid.UUID(payload["account_id"])
    sub = _get_or_create_subscription(db, account_id)

    checkout_url = create_checkout_session(
        sub.stripe_customer_id, body.plan_tier,
        success_url=f"{settings.frontend_base_url}/app/billing?checkout=success",
        cancel_url=f"{settings.frontend_base_url}/app/billing?checkout=cancelled",
    )
    return CheckoutSessionResponse(checkout_url=checkout_url)


@router.post("/billing/upgrade", response_model=SubscriptionResponse)
@router.post("/billing/downgrade", response_model=SubscriptionResponse)
def change_plan(
    body: PlanChangeRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    require_owner(payload)
    if body.plan_tier not in VALID_PLANS | {"free"}:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_plan", "message": "invalid plan_tier.", "details": {}}})

    account_id = uuid.UUID(payload["account_id"])
    sub = db.query(Subscription).filter(Subscription.account_id == account_id).first()
    if sub is None or sub.stripe_subscription_id is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "no_active_subscription", "message": "No active subscription to change.", "details": {}}})

    if body.plan_tier != "free":
        update_subscription_plan(sub.stripe_subscription_id, body.plan_tier)
    sub.plan_tier = body.plan_tier
    db.commit()
    db.refresh(sub)
    return SubscriptionResponse(account_id=sub.account_id, plan_tier=sub.plan_tier, status=sub.status, current_period_end=sub.current_period_end)


@router.post("/billing/refund", status_code=status.HTTP_201_CREATED)
def refund(
    body: RefundRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    require_owner(payload)
    account_id = uuid.UUID(payload["account_id"])

    invoice = db.query(Invoice).filter(Invoice.stripe_invoice_id == body.stripe_invoice_id, Invoice.account_id == account_id).first()
    if invoice is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "invoice_not_found", "message": "Invoice not found for this account.", "details": {}}})

    stripe_refund = create_refund(body.stripe_invoice_id, body.reason)

    db.add(OutboxEvent(
        event_type="refund.issued",
        payload={"account_id": str(account_id), "stripe_refund_id": stripe_refund["id"], "amount_cents": invoice.amount_cents, "reason": body.reason},
        account_id=account_id,
    ))
    db.commit()
    return {"status": "refund_issued", "stripe_refund_id": stripe_refund["id"]}


@router.get("/billing/invoices", response_model=list[InvoiceResponse])
def list_invoices(
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_payload),
):
    require_owner(payload)
    account_id = uuid.UUID(payload["account_id"])
    invoices = db.query(Invoice).filter(Invoice.account_id == account_id).order_by(Invoice.created_at.desc()).all()
    return [InvoiceResponse(id=i.id, stripe_invoice_id=i.stripe_invoice_id, amount_cents=i.amount_cents, status=i.status, created_at=i.created_at) for i in invoices]