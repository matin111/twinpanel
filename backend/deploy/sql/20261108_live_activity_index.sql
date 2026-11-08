-- TwinPanel RC.715+: non-blocking read-path optimization for live presence.
-- Run outside an explicit transaction, only after a verified backup:
--   sudo -u postgres psql -d twinpanel -v ON_ERROR_STOP=1 -f backend/deploy/sql/20261108_live_activity_index.sql
--
-- The live-status endpoint queries recent accepted usage by reported_at, not created_at.
-- This partial index avoids scanning historical quota events (660k+ rows observed).
-- It does not change traffic_used_bytes, counters, session status, or subscription expiry.
SET lock_timeout = '2s';
SET statement_timeout = '180s';
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_quota_usage_recent_accepted
    ON public.quota_usage_events (reported_at DESC, subscription_id, protocol)
    WHERE accepted_bytes > 0;
RESET statement_timeout;
RESET lock_timeout;
-- Verify with pg_indexes and EXPLAIN ANALYZE after installation.
-- Note: interrupted CREATE INDEX CONCURRENTLY may leave an INVALID index:
-- inspect pg_index.indisvalid and drop invalid index CONCURRENTLY before retry.
