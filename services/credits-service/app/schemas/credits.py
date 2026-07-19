from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class LedgerEntry(BaseModel):
    id: str
    account_id: str
    amount: int
    transaction_type: str
    reference_id: Optional[str]
    created_at: datetime

class BalanceResponse(BaseModel):
    account_id: str
    balance: int

class MarketplaceCreate(BaseModel):
    amount: int
    price_cents: int

class MarketplaceResponse(BaseModel):
    id: str
    seller_account_id: str
    amount: int
    price_cents: int
    status: str