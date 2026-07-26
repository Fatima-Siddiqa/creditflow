"""One-off: docker compose exec auth-service python scripts/grant_superadmin.py you@example.com"""
import sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models import User

if __name__ == "__main__":
    email = sys.argv[1]
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        print(f"No user with email {email}"); sys.exit(1)
    user.platform_role = "superadmin"
    db.commit()
    print(f"{email} is now platform_role=superadmin. They must log out/in (or refresh) to get a token carrying the new claim.")