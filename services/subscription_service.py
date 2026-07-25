"""
Subscription business logic and pricing calculations.
"""

from __future__ import annotations

import json
from calendar import monthrange
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models import Invoice, MembershipSubscription
from repositories.invoice_repository import InvoiceRepository
from repositories.subscription_repository import SubscriptionRepository
from schemas.subscription import (
    PlanFamilyResponse,
    PlanOptionResponse,
    SubscriptionResponse,
)
from services.notification_service import NotificationService


class MemberNotFoundError(Exception):
    """Raised when a member does not exist."""


class PlanNotFoundError(Exception):
    """Raised when a membership plan does not exist."""


class SubscriptionConflictError(Exception):
    """Raised when assigning a subscription overlaps with active dates."""


@dataclass
class ExpiringResult:
    items: list[SubscriptionResponse]
    total_items: int


class SubscriptionService:
    """Business logic for membership plans and subscriptions."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = SubscriptionRepository(db)
        self.invoice_repo = InvoiceRepository(db)
        self.notifier = NotificationService()

    @staticmethod
    def _to_money(value: Decimal | float | int) -> Decimal:
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _add_months(start_date: date, months: int) -> date:
        month = start_date.month - 1 + months
        year = start_date.year + month // 12
        month = month % 12 + 1
        day = min(start_date.day, monthrange(year, month)[1])
        return date(year, month, day)

    def sync_expired_subscriptions(self) -> None:
        today = date.today()
        expired = self.repo.list_expired_subscriptions(today=today)
        if not expired:
            return

        for row in expired:
            row.status = "expired"
        self.db.commit()

    def get_plan_catalog(self) -> list[PlanFamilyResponse]:
        plans = self.repo.list_active_plans()

        grouped: dict[str, PlanFamilyResponse] = {}
        for plan in plans:
            family_key = plan.family_name.upper()
            if family_key not in grouped:
                includes = []
                if plan.includes_json:
                    try:
                        includes = [str(item) for item in json.loads(plan.includes_json)]
                    except json.JSONDecodeError:
                        includes = []

                grouped[family_key] = PlanFamilyResponse(
                    family=family_key,
                    description=plan.description or "",
                    includes=includes,
                    options=[],
                )

            base_price = self._to_money(plan.base_price)
            tax_percent = self._to_money(plan.tax_percent)
            tax_amount = self._to_money(base_price * tax_percent / Decimal("100"))
            total_price = self._to_money(base_price + tax_amount)

            grouped[family_key].options.append(
                PlanOptionResponse(
                    id=plan.id,
                    sku=plan.name,
                    label=plan.name,
                    variant=plan.variant_name,
                    duration_months=plan.duration_months,
                    duration_label=plan.duration_label,
                    base_price=float(base_price),
                    tax_percent=float(tax_percent),
                    tax_amount=float(tax_amount),
                    total_price=float(total_price),
                )
            )

        return list(grouped.values())

    def assign_subscription(
        self,
        member_id: int,
        plan_id: int,
        start_date: date,
    ) -> tuple[SubscriptionResponse, list[dict]]:
        member = self.repo.get_member_by_id(member_id)
        if not member:
            raise MemberNotFoundError("Member not found")

        plan = self.repo.get_active_plan_by_id(plan_id)
        if not plan:
            raise PlanNotFoundError("Membership plan not found")

        overlap = self.repo.get_overlapping_active_subscription(member_id=member_id, start_date=start_date)
        if overlap:
            raise SubscriptionConflictError("Member already has an active subscription in this period")

        base_price = self._to_money(plan.base_price)
        tax_percent = self._to_money(plan.tax_percent)
        tax_amount = self._to_money(base_price * tax_percent / Decimal("100"))
        total_amount = self._to_money(base_price + tax_amount)

        end_date = self._add_months(start_date, plan.duration_months) - timedelta(days=1)

        row = MembershipSubscription(
            member_id=member_id,
            plan_id=plan.id,
            start_date=start_date,
            end_date=end_date,
            status="active",
            base_price=float(base_price),
            tax_percent=float(tax_percent),
            tax_amount=float(tax_amount),
            total_amount=float(total_amount),
        )

        invoice = Invoice(
            member_id=member_id,
            subscription_id=0,
            amount=float(total_amount),
            status="pending",
        )

        try:
            row = self.repo.create_subscription(row)
            invoice.subscription_id = row.id
            self.invoice_repo.create_invoice(invoice)
            self.db.commit()
            self.db.refresh(row)
            self.db.refresh(invoice)
        except Exception:
            self.db.rollback()
            raise

        # Notifications are best-effort for dummy integrations and should not fail assignment.
        welcome_results = self.notifier.send_welcome(
            member_name=member.full_name,
            email=member.email,
            phone=member.phone,
            plan_label=plan.name,
            start_date=row.start_date,
            end_date=row.end_date,
        )
        invoice_results = self.notifier.send_invoice_issued(
            member_name=member.full_name,
            email=member.email,
            phone=member.phone,
            invoice_id=invoice.id,
            amount=float(invoice.amount),
        )

        notifications = [asdict(item) for item in [*welcome_results, *invoice_results]]
        return self._to_subscription_response(row), notifications

    def get_member_subscriptions(self, member_id: int) -> list[SubscriptionResponse]:
        member = self.repo.get_member_by_id(member_id)
        if not member:
            raise MemberNotFoundError("Member not found")

        rows = self.repo.list_member_subscriptions(member_id)
        return [self._to_subscription_response(row) for row in rows]

    def get_expiring_subscriptions(self, days: int, page: int, page_size: int) -> ExpiringResult:
        today = date.today()
        limit_date = today + timedelta(days=days)

        rows, total_items = self.repo.list_expiring_subscriptions(
            from_date=today,
            to_date=limit_date,
            page=page,
            page_size=page_size,
        )

        return ExpiringResult(
            items=[self._to_subscription_response(row) for row in rows],
            total_items=total_items,
        )

    @staticmethod
    def _to_subscription_response(row: MembershipSubscription) -> SubscriptionResponse:
        plan = row.plan
        return SubscriptionResponse(
            id=row.id,
            member_id=row.member_id,
            plan_id=row.plan_id,
            plan_family=plan.family_name.upper(),
            plan_variant=plan.variant_name,
            plan_label=plan.name,
            start_date=row.start_date,
            end_date=row.end_date,
            status=row.status,
            base_price=float(row.base_price),
            tax_percent=float(row.tax_percent),
            tax_amount=float(row.tax_amount),
            total_amount=float(row.total_amount),
        )
