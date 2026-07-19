from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum, Float
from sqlalchemy.sql import func
from app.db import Base
import enum

class TransactionType(str, enum.Enum):
    PURCHASE = "purchase"
    CONSUMPTION = "consumption"
    MARKETPLACE_BUY = "marketplace_buy"
    MARKETPLACE_SELL = "marketplace_sell"
    REFUND_CLAWBACK = "refund_clawback"

class CreditLedger(Base):
    __tablename__ = "credits_ledger"

    id = Column(String, primary_key=True, index=True)
    account_id = Column(String, index=True, nullable=False)
    amount = Column(Integer, nullable=False) # Positive for credit, negative for debit
    transaction_type = Column(Enum(TransactionType), nullable=False)
    reference_id = Column(String, nullable=True) # e.g., invoice_id or marketplace_listing_id
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"

    id = Column(String, primary_key=True, index=True)
    seller_account_id = Column(String, index=True, nullable=False)
    amount = Column(Integer, nullable=False)
    price_cents = Column(Integer, nullable=False)
    status = Column(String, default="active") # active, sold, cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id = Column(String, primary_key=True, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())