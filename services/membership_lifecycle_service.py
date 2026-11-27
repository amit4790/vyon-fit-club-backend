"""Pause/resume, renewal stacking, and conversion orchestration."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.membership_lifecycle import (
    ASSIGNMENT_INTENT_CONVERSION,
    ASSIGNMENT_INTENT_NEW,
    ASSIGNMENT_INTENT_RENEW,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_PAUSED,
    STATUS_SCHEDULED,
    TERMINAL_STATUSES,
    end_date_for_remaining_days,
    is_effective_active,
    purchased_inclusive_days,
    remaining_days_from_today,
)
from models import Member, MembershipSubscription
from repositories.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)

WaitRelation = Literal["paused_wait", "scheduled_wait"]

_UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _paused_queue_sort_key(row: MembershipSubscription) -> tuple:
    paused = row.paused_at or row.created_at or _UTC_MIN
    return (paused, row.id)


def _scheduled_queue_sort_key(row: MembershipSubscription) -> tuple:
    created = row.created_at or _UTC_MIN
    return (row.start_date, created, row.id)


class InvalidLifecycleTransitionError(Exception):
    """Raised when a status transition is not allowed."""


class EffectiveMembershipConflictError(Exception):
    """Another active membership is already effective for this member."""


class MembershipLifecycleService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SubscriptionRepository(db)

    def lock_member_for_lifecycle(self, member_id: int) -> Member:
        """
        Acquire lifecycle locks in a fixed order: parent member row, then subscription rows.

        Callers performing lifecycle writes must hold this lock for the duration of their
        transaction. Works when the member has zero subscriptions.
        """
        member = (
            self.db.execute(
                select(Member)
                .where(Member.id == member_id, Member.deleted_at.is_(None))
                .with_for_update()
            )
            .scalar_one_or_none()
        )
        if member is None:
            raise InvalidLifecycleTransitionError("Member not found for lifecycle lock")

        self.db.execute(
            select(MembershipSubscription.id)
            .where(MembershipSubscription.member_id == member_id)
            .order_by(MembershipSubscription.id.asc())
            .with_for_update()
        )
        return member

    def lock_member_subscriptions(self, member_id: int) -> None:
        """Deprecated alias — use lock_member_for_lifecycle."""
        self.lock_member_for_lifecycle(member_id)

    def get_effective_active(self, member_id: int, today: date) -> MembershipSubscription | None:
        rows = self.repo.list_member_subscriptions(member_id)
        for row in rows:
            if is_effective_active(
                status=row.status,
                start_date=row.start_date,
                end_date=row.end_date,
                today=today,
            ):
                return row
        return None

    def validate_and_set_resume_after(
        self,
        child: MembershipSubscription,
        predecessor_id: int | None,
        *,
        relation: WaitRelation,
    ) -> None:
        """Central validation for resume_after subscription queue links."""
        if predecessor_id is None:
            child.resume_after_subscription_id = None
            return
        if predecessor_id == child.id:
            raise InvalidLifecycleTransitionError("Subscription cannot wait on itself")

        predecessor = self.repo.get_subscription_by_id(predecessor_id)
        if predecessor is None:
            raise InvalidLifecycleTransitionError("Predecessor subscription not found")
        if predecessor.member_id != child.member_id:
            raise InvalidLifecycleTransitionError("Predecessor does not belong to the same member")
        if predecessor.status in TERMINAL_STATUSES:
            raise InvalidLifecycleTransitionError("Cannot wait on a terminal subscription")

        if relation == "paused_wait" and child.status != STATUS_PAUSED:
            raise InvalidLifecycleTransitionError("Only paused subscriptions use paused wait links")
        if relation == "scheduled_wait" and child.status != STATUS_SCHEDULED:
            raise InvalidLifecycleTransitionError("Only scheduled subscriptions use scheduled wait links")

        prior = child.resume_after_subscription_id
        child.resume_after_subscription_id = predecessor_id
        try:
            self._assert_resume_chain_acyclic(
                child.id,
                member_id=child.member_id,
                new_predecessor_id=predecessor_id,
            )
        except InvalidLifecycleTransitionError:
            child.resume_after_subscription_id = prior
            raise

    def _load_member_resume_edges(self, member_id: int) -> dict[int, int]:
        """Map subscription_id -> resume_after_predecessor_id (non-null only)."""
        rows = self.db.execute(
            select(MembershipSubscription).where(MembershipSubscription.member_id == member_id)
        ).scalars().all()
        return {
            row.id: row.resume_after_subscription_id
            for row in rows
            if row.resume_after_subscription_id is not None
        }

    def _assert_resume_chain_acyclic(
        self,
        from_subscription_id: int,
        *,
        member_id: int,
        new_predecessor_id: int | None = None,
    ) -> None:
        edges = self._load_member_resume_edges(member_id)

        if new_predecessor_id is not None:
            walk = new_predecessor_id
            seen_up: set[int] = {from_subscription_id}
            while walk is not None:
                if walk in seen_up:
                    raise InvalidLifecycleTransitionError("Resume chain would form a cycle")
                seen_up.add(walk)
                walk = edges.get(walk)
                if walk == from_subscription_id:
                    raise InvalidLifecycleTransitionError("Resume chain would form a cycle")

        successor_map: dict[int, list[int]] = {}
        for child_id, pred_id in edges.items():
            successor_map.setdefault(pred_id, []).append(child_id)

        seen: set[int] = {from_subscription_id}
        stack = list(successor_map.get(from_subscription_id, []))
        while stack:
            current = stack.pop()
            if current in seen:
                raise InvalidLifecycleTransitionError("Resume chain would form a cycle")
            seen.add(current)
            stack.extend(successor_map.get(current, []))

        if self._find_resume_cycle_nodes(edges):
            raise InvalidLifecycleTransitionError(
                "Existing corrupt resume relationship cycle must be repaired before adding links"
            )

    def _find_resume_cycle_nodes(self, edges: dict[int, int]) -> list[int] | None:
        """Return node ids participating in a cycle, if any."""
        visited: set[int] = set()
        for start in edges:
            if start in visited:
                continue
            path: list[int] = []
            index: dict[int, int] = {}
            node = start
            while node is not None and node not in visited:
                if node in index:
                    cycle_start = index[node]
                    return path[cycle_start:]
                index[node] = len(path)
                path.append(node)
                node = edges.get(node)
            visited.update(path)
        return None

    def pause_subscription(
        self,
        subscription: MembershipSubscription,
        *,
        today: date,
        resume_after_subscription_id: int | None = None,
    ) -> None:
        if subscription.status != STATUS_ACTIVE:
            raise InvalidLifecycleTransitionError("Only active subscriptions can be paused")

        remaining = remaining_days_from_today(
            start_date=subscription.start_date,
            end_date=subscription.end_date,
            today=today,
        )
        subscription.status = STATUS_PAUSED
        subscription.paused_at = datetime.now(timezone.utc)
        subscription.remaining_days = remaining
        self.validate_and_set_resume_after(
            subscription,
            resume_after_subscription_id,
            relation="paused_wait",
        )

    def _chain_duplicate_paused_siblings(
        self,
        waiting: list[MembershipSubscription],
        *,
        member_id: int,
        completed_subscription_id: int,
    ) -> list[MembershipSubscription]:
        """Resume the first in queue order; chain the rest behind it without losing remaining_days."""
        ordered = sorted(waiting, key=_paused_queue_sort_key)
        if len(ordered) <= 1:
            return ordered

        logger.warning(
            "Multiple paused subscriptions shared the same predecessor; chaining in queue order",
            extra={
                "member_id": member_id,
                "completed_subscription_id": completed_subscription_id,
                "paused_count": len(ordered),
                "paused_ids": [row.id for row in ordered],
            },
        )
        head = ordered[0]
        previous = head
        for sibling in ordered[1:]:
            if sibling.status != STATUS_PAUSED:
                continue
            self.validate_and_set_resume_after(sibling, previous.id, relation="paused_wait")
            previous = sibling
        return [head]

    def _chain_duplicate_scheduled_siblings(
        self,
        waiting: list[MembershipSubscription],
        *,
        member_id: int,
        completed_subscription_id: int,
    ) -> MembershipSubscription:
        """Pick first scheduled term; chain siblings behind it in purchase order."""
        ordered = sorted(waiting, key=_scheduled_queue_sort_key)
        if len(ordered) == 1:
            return ordered[0]

        logger.warning(
            "Multiple scheduled renewals shared the same predecessor; chaining in purchase order",
            extra={
                "member_id": member_id,
                "completed_subscription_id": completed_subscription_id,
                "scheduled_count": len(ordered),
                "scheduled_ids": [row.id for row in ordered],
            },
        )
        for index in range(1, len(ordered)):
            self.validate_and_set_resume_after(
                ordered[index],
                ordered[index - 1].id,
                relation="scheduled_wait",
            )
        return ordered[0]

    def resume_subscription_from_pause(
        self,
        subscription: MembershipSubscription,
        *,
        today: date,
    ) -> None:
        if subscription.status == STATUS_ACTIVE:
            return
        if subscription.status != STATUS_PAUSED:
            raise InvalidLifecycleTransitionError("Only paused subscriptions can resume")
        if subscription.remaining_days is None or subscription.remaining_days <= 0:
            subscription.status = STATUS_EXPIRED
            return

        remaining = int(subscription.remaining_days)
        subscription.status = STATUS_ACTIVE
        subscription.start_date = today
        subscription.end_date = end_date_for_remaining_days(start=today, remaining_days=remaining)
        subscription.resumed_at = datetime.now(timezone.utc)
        subscription.resume_after_subscription_id = None
        subscription.remaining_days = None
        subscription.paused_at = None

    def complete_subscription_and_continue(
        self,
        subscription: MembershipSubscription,
        *,
        today: date,
        terminal_status: str = STATUS_EXPIRED,
        assume_lock_held: bool = False,
    ) -> list[int]:
        """
        Mark subscription terminal (expired/cancelled) and resume paused/scheduled successors.
        Returns member_ids that may need device access sync.
        """
        if terminal_status not in {STATUS_EXPIRED, STATUS_CANCELLED}:
            raise InvalidLifecycleTransitionError(f"Unsupported terminal status: {terminal_status}")
        if subscription.status in {STATUS_EXPIRED, STATUS_CANCELLED}:
            return []
        if subscription.status != STATUS_ACTIVE:
            return []

        member_id = subscription.member_id
        if not assume_lock_held:
            self.lock_member_for_lifecycle(member_id)

        subscription.status = terminal_status
        completed_id = subscription.id
        affected = {member_id}

        waiting_paused = self.repo.list_paused_waiting_for_subscription(completed_id)
        paused_to_resume = self._chain_duplicate_paused_siblings(
            waiting_paused,
            member_id=member_id,
            completed_subscription_id=completed_id,
        )

        for paused in paused_to_resume:
            if paused.status != STATUS_PAUSED:
                continue
            try:
                self.resume_subscription_from_pause(paused, today=today)
            except InvalidLifecycleTransitionError:
                continue
            logger.info(
                "Resumed paused subscription after predecessor ended",
                extra={
                    "member_id": member_id,
                    "paused_subscription_id": paused.id,
                    "completed_subscription_id": completed_id,
                    "terminal_status": terminal_status,
                },
            )

        waiting_scheduled = self.repo.list_scheduled_waiting_for_subscription(completed_id)
        if waiting_scheduled:
            first_scheduled = self._chain_duplicate_scheduled_siblings(
                waiting_scheduled,
                member_id=member_id,
                completed_subscription_id=completed_id,
            )
            try:
                self.activate_scheduled_subscription(first_scheduled, today=today)
            except InvalidLifecycleTransitionError:
                pass

        if self.get_effective_active(member_id, today) is None:
            for sched in self.repo.list_orphan_scheduled_ready(member_id, today):
                try:
                    self.activate_scheduled_subscription(sched, today=today)
                except InvalidLifecycleTransitionError:
                    continue
                break

        return list(affected)

    def activate_scheduled_subscription(
        self,
        subscription: MembershipSubscription,
        *,
        today: date,
    ) -> None:
        if subscription.status == STATUS_ACTIVE:
            return
        if subscription.status != STATUS_SCHEDULED:
            raise InvalidLifecycleTransitionError("Only scheduled subscriptions can be activated")

        purchased_days = purchased_inclusive_days(
            start_date=subscription.start_date,
            end_date=subscription.end_date,
        )
        if purchased_days <= 0:
            subscription.status = STATUS_EXPIRED
            subscription.resume_after_subscription_id = None
            return

        activation_start = today
        subscription.start_date = activation_start
        subscription.end_date = end_date_for_remaining_days(
            start=activation_start,
            remaining_days=purchased_days,
        )
        subscription.status = STATUS_ACTIVE
        subscription.resume_after_subscription_id = None
        logger.info(
            "Activated scheduled subscription with preserved purchased duration",
            extra={
                "member_id": subscription.member_id,
                "subscription_id": subscription.id,
                "purchased_days": purchased_days,
                "activation_start": activation_start.isoformat(),
            },
        )

    def _renewal_queue_tail(self, head: MembershipSubscription) -> MembershipSubscription:
        """Walk scheduled children from an active anchor; isolated from unrelated chains."""
        current = head
        while True:
            children = self.repo.list_scheduled_waiting_for_subscription(current.id)
            if not children:
                return current
            if len(children) > 1:
                ordered = sorted(children, key=_scheduled_queue_sort_key)
                logger.warning(
                    "Multiple scheduled children on renewal queue tail walk; using purchase-ordered tail",
                    extra={
                        "member_id": current.member_id,
                        "predecessor_subscription_id": current.id,
                        "scheduled_ids": [row.id for row in ordered],
                    },
                )
                current = ordered[-1]
            else:
                current = children[0]

    def get_renewal_stack_anchor(self, member_id: int, today: date) -> MembershipSubscription | None:
        """Tail of the effective active subscription's own scheduled renewal chain."""
        effective = self.get_effective_active(member_id, today)
        if effective is None:
            return None
        return self._renewal_queue_tail(effective)

    def cancel_active_subscription_and_continue(
        self,
        subscription: MembershipSubscription,
        *,
        today: date,
        assume_lock_held: bool = False,
    ) -> list[int]:
        """Immediate cancellation of an active subscription; resume paused successors (LIFO)."""
        return self.complete_subscription_and_continue(
            subscription,
            today=today,
            terminal_status=STATUS_CANCELLED,
            assume_lock_held=assume_lock_held,
        )

    def validate_new_assignment(
        self,
        member_id: int,
        *,
        intent: str,
        start_date: date,
        today: date,
        assume_lock_held: bool = False,
    ) -> tuple[date, MembershipSubscription | None]:
        """
        Return (effective start_date, renewal anchor for scheduled renew).

        Caller must hold ``lock_member_for_lifecycle`` when ``assume_lock_held`` is True.
        """
        if not assume_lock_held:
            self.lock_member_for_lifecycle(member_id)

        renew_anchor: MembershipSubscription | None = None

        if intent == ASSIGNMENT_INTENT_NEW:
            return start_date, renew_anchor

        if intent == ASSIGNMENT_INTENT_RENEW:
            renew_anchor = self.get_renewal_stack_anchor(member_id, today)
            if renew_anchor is None:
                return start_date, renew_anchor
            stacked_start = renew_anchor.end_date + timedelta(days=1)
            if start_date < stacked_start:
                return stacked_start, renew_anchor
            return start_date, renew_anchor

        if intent == ASSIGNMENT_INTENT_CONVERSION:
            return start_date, renew_anchor

        raise InvalidLifecycleTransitionError(f"Unknown assignment intent: {intent}")

    def supersede_effective_active_if_required(
        self,
        member_id: int,
        *,
        intent: str,
        today: date,
    ) -> MembershipSubscription | None:
        """
        For non-renew assignments: pause the current effective membership so the new
        term can become active without overlapping effective access.
        """
        if intent == ASSIGNMENT_INTENT_RENEW:
            return None

        effective = self.get_effective_active(member_id, today)
        if effective is None:
            if intent == ASSIGNMENT_INTENT_CONVERSION:
                raise InvalidLifecycleTransitionError("No effective membership to convert from")
            return None

        self.pause_subscription(effective, today=today)
        return effective

    def resolve_initial_status(
        self,
        *,
        intent: str,
        start_date: date,
        today: date,
    ) -> str:
        if intent == ASSIGNMENT_INTENT_RENEW and start_date > today:
            return STATUS_SCHEDULED
        return STATUS_ACTIVE

    def link_paused_subscriptions_to_new_active(
        self,
        member_id: int,
        *,
        new_active_id: int,
        pause_effective_id: int,
        today: date,
    ) -> None:
        del today  # reserved for future backdating rules
        effective = self.repo.get_subscription_by_id(pause_effective_id)
        if effective is None:
            raise InvalidLifecycleTransitionError("Effective subscription not found for conversion")
        if effective.member_id != member_id:
            raise InvalidLifecycleTransitionError("Subscription does not belong to member")
        if effective.status != STATUS_PAUSED:
            raise InvalidLifecycleTransitionError("Expected paused subscription after conversion pause")

        self.validate_and_set_resume_after(effective, new_active_id, relation="paused_wait")

    def link_scheduled_renewal_to_anchor(
        self,
        subscription: MembershipSubscription,
        *,
        anchor: MembershipSubscription,
    ) -> None:
        if subscription.status != STATUS_SCHEDULED:
            return
        if anchor.member_id != subscription.member_id:
            raise InvalidLifecycleTransitionError("Renewal anchor does not belong to member")
        self.validate_and_set_resume_after(subscription, anchor.id, relation="scheduled_wait")

    def assert_can_activate_status(self, current: str, new: str) -> None:
        if current in TERMINAL_STATUSES and new not in {STATUS_EXPIRED, STATUS_CANCELLED}:
            raise InvalidLifecycleTransitionError(f"Cannot transition from {current} to {new}")
        allowed = {
            STATUS_ACTIVE: {STATUS_PAUSED, STATUS_EXPIRED, STATUS_CANCELLED},
            STATUS_PAUSED: {STATUS_ACTIVE, STATUS_EXPIRED, STATUS_CANCELLED},
            STATUS_SCHEDULED: {STATUS_ACTIVE, STATUS_CANCELLED, STATUS_EXPIRED},
            STATUS_EXPIRED: set(),
            STATUS_CANCELLED: set(),
        }
        if current == new:
            return
        if new not in allowed.get(current, set()) and current not in TERMINAL_STATUSES:
            if not (current == STATUS_ACTIVE and new == STATUS_SCHEDULED):
                raise InvalidLifecycleTransitionError(f"Invalid transition {current} -> {new}")