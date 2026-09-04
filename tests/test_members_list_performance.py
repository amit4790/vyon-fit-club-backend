"""Members list enrichment, filter/sort pagination, and no sync on read GETs."""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Invoice, Member, MembershipPlan, MembershipSubscription
from routes import admin as admin_routes
from services.member_service import MemberService
from services.subscription_service import SubscriptionService


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_plan(db: Session) -> MembershipPlan:
    plan = MembershipPlan(
        name="VYON BASIC - 1 Month",
        family_name="VYON BASIC",
        variant_name=None,
        duration_months=1,
        duration_label="1 Month",
        duration_days=30,
        base_price=1000,
        tax_percent=5,
        total_price=1050,
        price=1050,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _seed_member(db: Session, *, name: str, mobile: str) -> Member:
    member = Member(
        full_name=name,
        mobile_number=mobile,
        joined_at=date.today(),
        status="active",
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _seed_subscription(
    db: Session,
    *,
    member: Member,
    plan: MembershipPlan,
    start: date,
    end: date,
    payment_status: str = "pending",
    status: str = "active",
) -> MembershipSubscription:
    row = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=start,
        end_date=end,
        duration_value=1,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status=payment_status,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_list_members_includes_membership_summary(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, name="Active Member", mobile="9000000001")
    today = date.today()
    _seed_subscription(
        db,
        member=member,
        plan=plan,
        start=today - timedelta(days=5),
        end=today + timedelta(days=25),
        payment_status="paid",
    )

    members, total, summaries = MemberService(db).list_members(page=1, page_size=10, search=None)
    assert total == 1
    assert len(members) == 1
    summary = summaries[member.id]
    assert summary.status_key == "active"
    assert summary.focus_subscription_id is not None
    assert summary.end_date == today + timedelta(days=25)
    assert summary.active_memberships


def test_list_members_filter_and_expiry_sort_paginates(db: Session):
    plan = _seed_plan(db)
    today = date.today()

    paid = _seed_member(db, name="Paid Soon", mobile="9000000002")
    unpaid = _seed_member(db, name="Unpaid Later", mobile="9000000003")
    none_member = _seed_member(db, name="No Plan", mobile="9000000004")
    expired = _seed_member(db, name="Expired", mobile="9000000005")

    _seed_subscription(
        db,
        member=paid,
        plan=plan,
        start=today - timedelta(days=20),
        end=today + timedelta(days=5),
        payment_status="paid",
    )
    _seed_subscription(
        db,
        member=unpaid,
        plan=plan,
        start=today - timedelta(days=2),
        end=today + timedelta(days=40),
        payment_status="pending",
    )
    _seed_subscription(
        db,
        member=expired,
        plan=plan,
        start=today - timedelta(days=60),
        end=today - timedelta(days=1),
        payment_status="paid",
        status="expired",
    )

    service = MemberService(db)

    none_page, none_total, _ = service.list_members(
        page=1, page_size=10, search=None, membership_status="none"
    )
    assert none_total == 1
    assert none_page[0].id == none_member.id

    unpaid_page, unpaid_total, unpaid_summaries = service.list_members(
        page=1, page_size=10, search=None, membership_status="inactive_unpaid"
    )
    assert unpaid_total == 1
    assert unpaid_page[0].id == unpaid.id
    assert unpaid_summaries[unpaid.id].status_key == "inactive_unpaid"

    expired_page, expired_total, _ = service.list_members(
        page=1, page_size=10, search=None, membership_status="expired"
    )
    assert expired_total == 1
    assert expired_page[0].id == expired.id

    sorted_page, sorted_total, _ = service.list_members(
        page=1, page_size=2, search=None, sort="expiry"
    )
    assert sorted_total == 4
    assert len(sorted_page) == 2
    # Soonest membership end_date first (expired yesterday before paid in 5 days).
    assert sorted_page[0].id == expired.id
    assert sorted_page[1].id == paid.id


def test_get_members_route_returns_summary_fields(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, name="HTTP Member", mobile="9000000006")
    today = date.today()
    sub = _seed_subscription(
        db,
        member=member,
        plan=plan,
        start=today,
        end=today + timedelta(days=10),
        payment_status="partial",
    )
    db.add(
        Invoice(
            member_id=member.id,
            subscription_id=sub.id,
            amount=1050,
            status="partial",
            total_paid=200,
            outstanding_balance=850,
            final_amount_received=1050,
        )
    )
    db.commit()

    response = admin_routes.get_members(page=1, page_size=10, search=None, membership_status=None, sort=None, db=db)
    assert response.pagination.total_items == 1
    row = response.data[0]
    assert row.id == member.id
    assert row.membership_status == "active_pending_payment"
    assert row.focus_subscription_id == sub.id
    assert row.membership_expiry_date == today + timedelta(days=10)
    assert row.active_memberships
    assert row.active_memberships[0].subscription_id == sub.id


def test_expiring_and_plans_get_do_not_call_sync(db: Session, monkeypatch):
    calls = {"count": 0}

    def _tracking(self):
        calls["count"] += 1

    monkeypatch.setattr(SubscriptionService, "sync_expired_subscriptions", _tracking)

    admin_routes.get_plan_catalog(db=db)
    admin_routes.get_expiring_subscriptions(days=7, page=1, page_size=10, db=db)
    admin_routes.export_expiring_subscriptions(days=7, db=db)

    assert calls["count"] == 0


def test_assign_subscription_still_syncs_expired(db: Session, monkeypatch):
    plan = _seed_plan(db)
    member = _seed_member(db, name="Assign Sync", mobile="9000000007")
    calls = {"count": 0}
    original = SubscriptionService.sync_expired_subscriptions

    def _tracking(self):
        calls["count"] += 1
        return original(self)

    monkeypatch.setattr(SubscriptionService, "sync_expired_subscriptions", _tracking)
    monkeypatch.setattr(
        SubscriptionService,
        "_sync_device_access_for_members",
        lambda self, member_ids: None,
    )

    SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today(),
        duration_value=1,
        duration_unit="months",
    )
    assert calls["count"] >= 1
