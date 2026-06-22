-- ============================================================
-- JazzyVault — Migration 006: AI Requests
-- ============================================================
-- Creates the `ai_requests` table, tracking every AI Document
-- Intelligence call: which file it was run against, what kind of
-- request (summarize/insights/simplify/translate/analyze), and the
-- model's response. Mirrors the pattern established by `conversions`
-- (Phase 4) — request tracked as a row, RLS scoped to the owner.
-- ============================================================

create table if not exists public.ai_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  file_id uuid not null references public.files(id) on delete cascade,
  request_type text not null
    check (request_type in ('summarize', 'insights', 'simplify', 'translate', 'analyze')),
  -- Free-form input the request needed beyond the file itself, e.g.
  -- the target language for a 'translate' request. Empty for the
  -- other request types.
  input_params jsonb not null default '{}'::jsonb,
  response text,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'failed')),
  error_message text,
  ai_provider text not null,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

comment on table public.ai_requests is 'AI Document Intelligence requests: summarization, insights, simplification, translation, analysis.';

create index if not exists idx_ai_requests_user_id on public.ai_requests(user_id);
create index if not exists idx_ai_requests_file_id on public.ai_requests(file_id);
create index if not exists idx_ai_requests_created_at on public.ai_requests(created_at desc);

-- --- Row Level Security -----------------------------------------

alter table public.ai_requests enable row level security;

drop policy if exists "Users can view their own AI requests" on public.ai_requests;
create policy "Users can view their own AI requests"
  on public.ai_requests for select
  using (auth.uid() = user_id);

drop policy if exists "Users can insert their own AI requests" on public.ai_requests;
create policy "Users can insert their own AI requests"
  on public.ai_requests for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users can update their own AI requests" on public.ai_requests;
create policy "Users can update their own AI requests"
  on public.ai_requests for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- No delete policy — AI request history is an audit trail, consistent
-- with the no-delete policy on `conversions` (Phase 4).
