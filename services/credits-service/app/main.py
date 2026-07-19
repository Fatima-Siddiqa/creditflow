from fastapi import FastAPI
from app.api import credits
from app.db import engine, Base
import threading
from app.events.billing_consumer import process_billing_event
# Assuming you have a standard rabbitmq connection script in your boilerplate
from app.events.rabbitmq import start_consuming 

# Create tables (In production, rely on Alembic, but this is a fallback)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Credits & Marketplace Service", version="1.0.0")

# Include the routers we created
app.include_router(credits.router, prefix="/credits", tags=["Credits"])

@app.on_event("startup")
def startup_event():
    # Start the RabbitMQ consumer in a background thread so it doesn't block the API
    consumer_thread = threading.Thread(
        target=start_consuming, 
        args=("billing.events", process_billing_event),
        daemon=True
    )
    consumer_thread.start()

@app.get("/health")
def health_check():
    return {"status": "healthy"}