from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LedgerEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    amount: int
    transaction_type: str
    reference_id: Optional[str] = None
    created_at: datetime


class BalanceResponse(BaseModel):
    account_id: str
    balance: int


class MarketplaceCreate(BaseModel):
    amount: int
    price_cents: int


class MarketplaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seller_account_id: str
    amount: int
    price_cents: int
    status: str