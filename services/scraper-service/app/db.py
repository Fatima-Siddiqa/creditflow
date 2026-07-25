from pymongo import MongoClient

from app.config import settings

_client = MongoClient(settings.mongo_url)
db = _client[settings.mongo_db_name]

scraped_documents = db["scraped_documents"]
scrape_jobs = db["scrape_jobs"]
recurring_jobs = db["recurring_jobs"]


def ping() -> None:
    """Used by /readyz. Raises on failure."""
    _client.admin.command("ping")