"""Read-only preflight before membership lifecycle migration."""
from sqlalchemy import create_engine, text
from core.config import settings

engine = create_engine(settings.database_url)
with engine.connect() as conn:
    dup = conn.execute(
        text(
            "SELECT member_id, COUNT(*) FROM membership_subscriptions "
            "WHERE status = 'active' GROUP BY member_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    stale = conn.execute(
        text(
            "SELECT COUNT(*) FROM membership_subscriptions "
            "WHERE status = 'active' AND end_date < CURRENT_DATE"
        )
    ).scalar()
    print("duplicate_active_members:", len(dup))
    for row in dup:
        print(f"  member_id={row[0]} active_count={row[1]}")
    print("stale_active_count:", stale)