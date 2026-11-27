-- Read-only production preflight: membership queue integrity (Phase 1.3.2)
-- Run against Neon; review output before any repair.

-- 1) Multiple orphan scheduled rows (no predecessor)
SELECT member_id, COUNT(*) AS orphan_count,
       array_agg(id ORDER BY start_date, created_at, id) AS subscription_ids
FROM membership_subscriptions
WHERE status = 'scheduled'
  AND resume_after_subscription_id IS NULL
GROUP BY member_id
HAVING COUNT(*) > 1;

-- 2) Broken predecessor (FK missing / deleted left NULL — should not happen if row exists)
SELECT child.id AS child_id, child.member_id, child.status, child.resume_after_subscription_id
FROM membership_subscriptions child
LEFT JOIN membership_subscriptions pred ON pred.id = child.resume_after_subscription_id
WHERE child.resume_after_subscription_id IS NOT NULL
  AND pred.id IS NULL;

-- 3) Cross-member resume_after links
SELECT child.id AS child_id, child.member_id AS child_member_id,
       pred.id AS pred_id, pred.member_id AS pred_member_id
FROM membership_subscriptions child
JOIN membership_subscriptions pred ON pred.id = child.resume_after_subscription_id
WHERE child.member_id <> pred.member_id;

-- 4) Paused / scheduled pointing at terminal predecessors
SELECT child.id, child.member_id, child.status, child.resume_after_subscription_id, pred.status AS pred_status
FROM membership_subscriptions child
JOIN membership_subscriptions pred ON pred.id = child.resume_after_subscription_id
WHERE child.status IN ('paused', 'scheduled')
  AND pred.status IN ('expired', 'cancelled');

-- 5) Multiple paused children on same predecessor (needs chain repair)
SELECT resume_after_subscription_id AS predecessor_id,
       COUNT(*) AS paused_count,
       array_agg(id ORDER BY paused_at NULLS LAST, created_at, id) AS paused_ids
FROM membership_subscriptions
WHERE status = 'paused'
  AND resume_after_subscription_id IS NOT NULL
GROUP BY resume_after_subscription_id
HAVING COUNT(*) > 1;

-- 6) Multiple scheduled children on same predecessor (needs chain repair)
SELECT resume_after_subscription_id AS predecessor_id,
       COUNT(*) AS scheduled_count,
       array_agg(id ORDER BY start_date, created_at, id) AS scheduled_ids
FROM membership_subscriptions
WHERE status = 'scheduled'
  AND resume_after_subscription_id IS NOT NULL
GROUP BY resume_after_subscription_id
HAVING COUNT(*) > 1;

-- 7) Self-references
SELECT id, member_id, status
FROM membership_subscriptions
WHERE resume_after_subscription_id = id;

-- 8) Duplicate effective active (should be zero with partial unique index)
SELECT member_id, COUNT(*) AS active_count, array_agg(id) AS ids
FROM membership_subscriptions
WHERE status = 'active'
GROUP BY member_id
HAVING COUNT(*) > 1;

-- Repair guidance (manual vs automatic):
-- * (5)(6) Same-member sibling queues: safe to auto-chain via app on next complete/assign (Phase 1.3.2).
-- * (3) Cross-member: MANUAL — verify member_id, clear or fix resume_after.
-- * (4) Terminal predecessor: MANUAL — re-link to correct non-terminal or run completion path if stale.
-- * (1) Orphans: MANUAL review — backfill resume_after using end_date+1 alignment; see Phase 1.3.1 notes.
-- * (7)(8) MANUAL — data corruption; never auto-expire paid rows.