"""subscription assignment flow

Revision ID: d4c85f91aa11
Revises: c3f4a1b29d0e
Create Date: 2026-07-24 13:45:00

"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4c85f91aa11"
down_revision: Union[str, Sequence[str], None] = "c3f4a1b29d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def upgrade() -> None:
    op.add_column("membership_plans", sa.Column("family_name", sa.String(length=50), nullable=True))
    op.add_column("membership_plans", sa.Column("variant_name", sa.String(length=50), nullable=True))
    op.add_column("membership_plans", sa.Column("duration_months", sa.Integer(), nullable=True))
    op.add_column("membership_plans", sa.Column("duration_label", sa.String(length=30), nullable=True))
    op.add_column("membership_plans", sa.Column("includes_json", sa.Text(), nullable=True))
    op.add_column("membership_plans", sa.Column("base_price", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "membership_plans",
        sa.Column("tax_percent", sa.Numeric(5, 2), nullable=False, server_default=sa.text("5.00")),
    )
    op.add_column("membership_plans", sa.Column("total_price", sa.Numeric(10, 2), nullable=True))

    op.add_column("membership_subscriptions", sa.Column("base_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("membership_subscriptions", sa.Column("tax_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("membership_subscriptions", sa.Column("tax_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("membership_subscriptions", sa.Column("total_amount", sa.Numeric(10, 2), nullable=True))

    conn = op.get_bind()

    plan_rows = [
        {
            "name": "VYON BASIC - 1 Month",
            "family_name": "VYON BASIC",
            "variant_name": "1 Month",
            "duration_months": 1,
            "duration_days": 30,
            "duration_label": "1 Month",
            "description": "Budget-friendly plan for getting started with gym access and guidance.",
            "includes": [
                "Gym access during standard hours",
                "Cardio and strength zones",
                "1 onboarding session",
                "Locker support",
            ],
            "base_price": 1800,
            "is_active": True,
        },
        {
            "name": "VYON BASIC - 3 Months",
            "family_name": "VYON BASIC",
            "variant_name": "3 Months",
            "duration_months": 3,
            "duration_days": 90,
            "duration_label": "3 Months",
            "description": "Budget-friendly plan for getting started with gym access and guidance.",
            "includes": [
                "Gym access during standard hours",
                "Cardio and strength zones",
                "1 onboarding session",
                "Locker support",
            ],
            "base_price": 5000,
            "is_active": True,
        },
        {
            "name": "VYON ADVANCE - 1 Month",
            "family_name": "VYON ADVANCE",
            "variant_name": "1 Month",
            "duration_months": 1,
            "duration_days": 30,
            "duration_label": "1 Month",
            "description": "Balanced plan with classes and trainer support for faster progress.",
            "includes": [
                "Everything in BASIC",
                "Group class access",
                "Monthly body composition tracking",
                "Nutrition guidance",
            ],
            "base_price": 2800,
            "is_active": True,
        },
        {
            "name": "VYON ADVANCE - 3 Months",
            "family_name": "VYON ADVANCE",
            "variant_name": "3 Months",
            "duration_months": 3,
            "duration_days": 90,
            "duration_label": "3 Months",
            "description": "Balanced plan with classes and trainer support for faster progress.",
            "includes": [
                "Everything in BASIC",
                "Group class access",
                "Monthly body composition tracking",
                "Nutrition guidance",
            ],
            "base_price": 7800,
            "is_active": True,
        },
        {
            "name": "VYON PRO - 1 Month",
            "family_name": "VYON PRO",
            "variant_name": "1 Month",
            "duration_months": 1,
            "duration_days": 30,
            "duration_label": "1 Month",
            "description": "Premium plan with personal coaching and performance optimization.",
            "includes": [
                "Everything in ADVANCE",
                "2 personal training sessions per month",
                "Priority support",
                "Recovery consultation",
            ],
            "base_price": 4200,
            "is_active": True,
        },
        {
            "name": "VYON PRO - 3 Months",
            "family_name": "VYON PRO",
            "variant_name": "3 Months",
            "duration_months": 3,
            "duration_days": 90,
            "duration_label": "3 Months",
            "description": "Premium plan with personal coaching and performance optimization.",
            "includes": [
                "Everything in ADVANCE",
                "2 personal training sessions per month",
                "Priority support",
                "Recovery consultation",
            ],
            "base_price": 11800,
            "is_active": True,
        },
    ]

    # Deactivate previously seeded legacy rows to avoid mixed catalogs in UI and APIs.
    conn.execute(sa.text("UPDATE membership_plans SET is_active = FALSE"))

    insert_stmt = sa.text(
        """
        INSERT INTO membership_plans
            (name, family_name, variant_name, description, duration_days, duration_months, duration_label,
             includes_json, base_price, tax_percent, total_price, price, is_active, created_at, updated_at)
        VALUES
            (:name, :family_name, :variant_name, :description, :duration_days, :duration_months, :duration_label,
             :includes_json, :base_price, :tax_percent, :total_price, :price, :is_active, NOW(), NOW())
        """
    )

    for row in plan_rows:
        base_price = _money(row["base_price"])
        tax_percent = _money(5)
        tax_amount = _money(base_price * tax_percent / 100)
        total_price = _money(base_price + tax_amount)

        conn.execute(
            insert_stmt,
            {
                "name": row["name"],
                "family_name": row["family_name"],
                "variant_name": row["variant_name"],
                "description": row["description"],
                "duration_days": row["duration_days"],
                "duration_months": row["duration_months"],
                "duration_label": row["duration_label"],
                "includes_json": json.dumps(row["includes"]),
                "base_price": base_price,
                "tax_percent": tax_percent,
                "total_price": total_price,
                "price": total_price,
                "is_active": row["is_active"],
            },
        )

    op.execute("UPDATE membership_subscriptions SET base_price = COALESCE(base_price, 0)")
    op.execute("UPDATE membership_subscriptions SET tax_percent = COALESCE(tax_percent, 5)")
    op.execute("UPDATE membership_subscriptions SET tax_amount = COALESCE(tax_amount, 0)")
    op.execute("UPDATE membership_subscriptions SET total_amount = COALESCE(total_amount, 0)")

    op.alter_column("membership_plans", "family_name", existing_type=sa.String(length=50), nullable=False)
    op.alter_column("membership_plans", "duration_months", existing_type=sa.Integer(), nullable=False)
    op.alter_column("membership_plans", "duration_label", existing_type=sa.String(length=30), nullable=False)
    op.alter_column("membership_plans", "base_price", existing_type=sa.Numeric(10, 2), nullable=False)
    op.alter_column("membership_plans", "total_price", existing_type=sa.Numeric(10, 2), nullable=False)

    op.alter_column("membership_subscriptions", "base_price", existing_type=sa.Numeric(10, 2), nullable=False)
    op.alter_column("membership_subscriptions", "tax_percent", existing_type=sa.Numeric(5, 2), nullable=False)
    op.alter_column("membership_subscriptions", "tax_amount", existing_type=sa.Numeric(10, 2), nullable=False)
    op.alter_column("membership_subscriptions", "total_amount", existing_type=sa.Numeric(10, 2), nullable=False)


def downgrade() -> None:
    op.drop_column("membership_subscriptions", "total_amount")
    op.drop_column("membership_subscriptions", "tax_amount")
    op.drop_column("membership_subscriptions", "tax_percent")
    op.drop_column("membership_subscriptions", "base_price")

    op.drop_column("membership_plans", "total_price")
    op.drop_column("membership_plans", "tax_percent")
    op.drop_column("membership_plans", "base_price")
    op.drop_column("membership_plans", "includes_json")
    op.drop_column("membership_plans", "duration_label")
    op.drop_column("membership_plans", "duration_months")
    op.drop_column("membership_plans", "variant_name")
    op.drop_column("membership_plans", "family_name")
