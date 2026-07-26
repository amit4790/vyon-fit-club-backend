"""update membership catalog pricing

Revision ID: f2a9b58d1c77
Revises: d4c85f91aa11
Create Date: 2026-07-25 00:00:00

"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a9b58d1c77"
down_revision: Union[str, Sequence[str], None] = "d4c85f91aa11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def upgrade() -> None:
    conn = op.get_bind()

    plan_rows = [
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
            "base_price": 7000,
            "is_active": True,
        },
        {
            "name": "VYON BASIC - 6 Months",
            "family_name": "VYON BASIC",
            "variant_name": "6 Months",
            "duration_months": 6,
            "duration_days": 180,
            "duration_label": "6 Months",
            "description": "Budget-friendly plan for getting started with gym access and guidance.",
            "includes": [
                "Gym access during standard hours",
                "Cardio and strength zones",
                "1 onboarding session",
                "Locker support",
            ],
            "base_price": 9000,
            "is_active": True,
        },
        {
            "name": "VYON BASIC - 12 Months",
            "family_name": "VYON BASIC",
            "variant_name": "12 Months",
            "duration_months": 12,
            "duration_days": 365,
            "duration_label": "12 Months",
            "description": "Budget-friendly plan for getting started with gym access and guidance.",
            "includes": [
                "Gym access during standard hours",
                "Cardio and strength zones",
                "1 onboarding session",
                "Locker support",
            ],
            "base_price": 14000,
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
            "base_price": 10000,
            "is_active": True,
        },
        {
            "name": "VYON ADVANCE - 6 Months",
            "family_name": "VYON ADVANCE",
            "variant_name": "6 Months",
            "duration_months": 6,
            "duration_days": 180,
            "duration_label": "6 Months",
            "description": "Balanced plan with classes and trainer support for faster progress.",
            "includes": [
                "Everything in BASIC",
                "Group class access",
                "Monthly body composition tracking",
                "Nutrition guidance",
            ],
            "base_price": 15000,
            "is_active": True,
        },
        {
            "name": "VYON ADVANCE - 12 Months",
            "family_name": "VYON ADVANCE",
            "variant_name": "12 Months",
            "duration_months": 12,
            "duration_days": 365,
            "duration_label": "12 Months",
            "description": "Balanced plan with classes and trainer support for faster progress.",
            "includes": [
                "Everything in BASIC",
                "Group class access",
                "Monthly body composition tracking",
                "Nutrition guidance",
            ],
            "base_price": 18000,
            "is_active": True,
        },
        {
            "name": "VYON PRO - Prime",
            "family_name": "VYON PRO",
            "variant_name": "Prime",
            "duration_months": 1,
            "duration_days": 30,
            "duration_label": "1 Month",
            "description": "Premium plan with personal coaching and performance optimization.",
            "includes": [
                "Everything in ADVANCE",
                "1:1 personal training sessions",
                "Customized diet plan",
                "Green Tea / Black Coffee"
                "Passive Stretching",
                "Foot Reflexology",
            ],
            "base_price": 12000,
            "is_active": True,
        },
        {
            "name": "VYON PRO - Elite",
            "family_name": "VYON PRO",
            "variant_name": "Elite",
            "duration_months": 1,
            "duration_days": 30,
            "duration_label": "1 Month",
            "description": "Premium plan with personal coaching and performance optimization.",
            "includes": [
                "Everything in ADVANCE",
                "1:1 personal training sessions",
                "Customized diet plan",
                "Green Tea / Black Coffee"
                "Passive Stretching",
                "Foot Reflexology",
            ],
            "base_price": 15000,
            "is_active": True,
        },
        {
            "name": "VYON PRO - Master",
            "family_name": "VYON PRO",
            "variant_name": "Master",
            "duration_months": 1,
            "duration_days": 30,
            "duration_label": "1 Month",
            "description": "Premium plan with personal coaching and performance optimization.",
            "includes": [
                "Everything in ADVANCE",
                "1:1 personal training sessions",
                "Customized diet plan",
                "Green Tea / Black Coffee"
                "Passive Stretching",
                "Foot Reflexology",
            ],
            "base_price": 18000,
            "is_active": True,
        },
    ]

    # Deactivate existing rows to keep a single active catalog for admin and landing pages.
    conn.execute(sa.text("UPDATE membership_plans SET is_active = FALSE"))

    insert_stmt = sa.text(
        """
        INSERT INTO membership_plans
            (name, family_name, variant_name, description, duration_days, duration_months, duration_label,
             includes_json, base_price, tax_percent, total_price, price, is_active, created_at, updated_at)
        VALUES
            (:name, :family_name, :variant_name, :description, :duration_days, :duration_months, :duration_label,
             :includes_json, :base_price, :tax_percent, :total_price, :price, :is_active, NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET
            family_name = EXCLUDED.family_name,
            variant_name = EXCLUDED.variant_name,
            description = EXCLUDED.description,
            duration_days = EXCLUDED.duration_days,
            duration_months = EXCLUDED.duration_months,
            duration_label = EXCLUDED.duration_label,
            includes_json = EXCLUDED.includes_json,
            base_price = EXCLUDED.base_price,
            tax_percent = EXCLUDED.tax_percent,
            total_price = EXCLUDED.total_price,
            price = EXCLUDED.price,
            is_active = EXCLUDED.is_active,
            updated_at = NOW()
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


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            UPDATE membership_plans
            SET is_active = FALSE
            WHERE name IN (
                'VYON BASIC - 3 Months',
                'VYON BASIC - 6 Months',
                'VYON BASIC - 12 Months',
                'VYON ADVANCE - 3 Months',
                'VYON ADVANCE - 6 Months',
                'VYON ADVANCE - 12 Months',
                'VYON PRO - Prime',
                'VYON PRO - Elite',
                'VYON PRO - Master'
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            UPDATE membership_plans
            SET is_active = TRUE
            WHERE name IN (
                'VYON BASIC - 1 Month',
                'VYON BASIC - 3 Months',
                'VYON ADVANCE - 1 Month',
                'VYON ADVANCE - 3 Months',
                'VYON PRO - 1 Month',
                'VYON PRO - 3 Months'
            )
            """
        )
    )
