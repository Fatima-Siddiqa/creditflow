import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_credits.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# Mock JWT verify for testing
def override_verify_jwt():
    return {"account_id": "test_acc_123", "role": "Owner"}
app.dependency_overrides[verify_jwt] = override_verify_jwt

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_get_empty_balance():
    response = client.get("/credits/balance")
    assert response.status_code == 200
    assert response.json()["balance"] == 0

def test_marketplace_listing_insufficient_funds():
    response = client.post("/credits/marketplace", json={
        "amount": 500,
        "price_cents": 1000
    })
    assert response.status_code == 400
    assert "Insufficient credits" in response.json()["detail"]