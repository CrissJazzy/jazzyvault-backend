-- ============================================================
-- JazzyVault — Migration 004: Activity Logs
-- ============================================================
-- Creates the `activity_logs` table, a unified feed of what a
-- user has done: uploads, conversions, downloads, deletes, and
-- (future-ready) AI requests. Existing Phase 2-4 services
-- (auth, files, conversion) are updated in this phase to write
-- to this table — it doesn't retroactively backfill history from
-- before this migration runs.
-- ============================================================

create table if not exists public.activity_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  activity_type text not null
    check (activity_type in (
      'file_upload',
      'file_delete',
      'file_download',
      'conversion_started',
      'conversion_completed',
      'conversion_failed',
      'ai_request'
    )),
  description text not null,
  -- Optional structured metadata (file_id, conversion_id, formats, etc.)
  -- so the frontend can deep-link from an activity row without parsing
  -- the description string.
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

comment on table public.activity_logs is 'Unified activity feed: uploads, deletes, downloads, conversions, and (future) AI requests.';

create index if not exists idx_activity_logs_user_id on public.activity_logs(user_id);
create index if not exists idx_activity_logs_created_at on public.activity_logs(created_at desc);
create index if not exists idx_activity_logs_type on public.activity_logs(activity_type);

-- --- Row Level Security -----------------------------------------

alter table public.activity_logs enable row level security;

drop policy if exists "Users can view their own activity" on public.activity_logs;
create policy "Users can view their own activity"
  on public.activity_logs for select
  using (auth.uid() = user_id);

drop policy if exists "Users can insert their own activity" on public.activity_logs;
create policy "Users can insert their own activity"
  on public.activity_logs for insert
  with check (auth.uid() = user_id);

-- No update/delete policies — activity logs are an immutable audit
-- trail. The backend writes these using the service-role client, which
-- bypasses RLS by design (see app/db/supabase_client.py), so this
-- policy mainly documents intent and protects against any future
-- direct-from-client write path.

-- --- Retention note -----------------------------------------------
-- No automatic pruning is configured. For a high-traffic production
-- deployment, consider a scheduled job (e.g. Supabase pg_cron) to
-- archive or delete rows older than N days/months, since this table
-- grows unboundedly with usage.
