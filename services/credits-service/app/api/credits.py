import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_payload
from app.models.ledger import CreditLedger, MarketplaceListing
from app.schemas.credits import BalanceResponse, LedgerEntry, MarketplaceCreate, MarketplaceResponse

router = APIRouter()


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": {}}}


@router.get("/balance", response_model=BalanceResponse)
def get_balance(db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    account_id = payload["account_id"]
    balance = db.query(func.sum(CreditLedger.amount)).filter(CreditLedger.account_id == account_id).scalar() or 0
    return {"account_id": account_id, "balance": balance}


@router.get("/history", response_model=list[LedgerEntry])
def get_history(db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    return db.query(CreditLedger).filter(CreditLedger.account_id == payload["account_id"]).order_by(CreditLedger.created_at.desc()).all()


@router.post("/marketplace", response_model=MarketplaceResponse)
def list_credits(listing: MarketplaceCreate, db: Session = Depends(get_db), payload: dict = Depends(get_current_payload)):
    account_id = payload["account_id"]

    current_balance = db.query(func.sum(CreditLedger.amount)).filter(CreditLedger.account_id == account_id).scalar() or 0
    if current_balance < listing.amount:
        raise HTTPException(status_code=400, detail=_error("insufficient_credits", "Insufficient credits to list."))

    new_listing = MarketplaceListing(
        id=str(uuid.uuid4()),
        seller_account_id=account_id,
        amount=listing.amount,
        price_cents=listing.price_cents,
    )
    db.add(new_listing)

    escrow_entry = CreditLedger(
        id=str(uuid.uuid4()),
        account_id=account_id,
        amount=-listing.amount,
        transaction_type="MARKETPLACE_SELL",
        reference_id=new_listing.id,
    )
    db.add(escrow_entry)
    db.commit()
    db.refresh(new_listing)
    return new_listing