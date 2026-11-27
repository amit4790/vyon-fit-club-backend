"""Local dev helper: resolve duplicate status='active' rows before lifecycle migration."""
from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import create_engine, text

sys.path.insert(0, ".")
from core.config import settings  # noqa: E402
from core.membership_lifecycle import is_effective_active  # noqa: E402


def main() -> int:
    engine = create_engine(settings.database_url)
    today = date.today()
    with engine.begin() as conn:
        dups = conn.execute(
            text(
                """
                SELECT member_id
                FROM membership_subscriptions
                WHERE status = 'active'
                GROUP BY member_id
                HAVING COUNT(*) > 1
                """
            )
        ).scalars().all()

        if not dups:
            print("No duplicate active memberships found.")
            return 0

        print(f"Members with duplicate active rows: {list(dups)}")
        for member_id in dups:
            rows = conn.execute(
                text(
                    """
                    SELECT id, start_date, end_date, payment_status, created_at
                    FROM membership_subscriptions
                    WHERE member_id = :member_id AND status = 'active'
                    ORDER BY end_date DESC, id DESC
                    """
                ),
                {"member_id": member_id},
            ).mappings().all()

            keep_id = None
            for row in rows:
                if is_effective_active(
                    status="active",
                    start_date=row["start_date"],
                    end_date=row["end_date"],
                    today=today,
                ):
                    keep_id = row["id"]
                    break
            if keep_id is None:
                keep_id = rows[0]["id"]

            for row in rows:
                if row["id"] == keep_id:
                    print(f"  keep member={member_id} subscription_id={row['id']}")
                    continue
                conn.execute(
                    text(
                        """
                        UPDATE membership_subscriptions
                        SET status = 'expired'
                        WHERE id = :id AND status = 'active'
                        """
                    ),
                    {"id": row["id"]},
                )
                print(f"  expired duplicate member={member_id} subscription_id={row['id']}")

    print("Remediation complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())