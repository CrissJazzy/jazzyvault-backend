-- ============================================================
-- JazzyVault — Migration 003: Conversions
-- ============================================================
-- Creates the `conversions` table, tracking every document
-- conversion job: which file went in, which file came out,
-- format, and status. Output files are stored as ordinary rows
-- in the `files` table (see Phase 3), so the vault and history
-- views can both reference them without duplicating storage logic.
-- ============================================================

create table if not exists public.conversions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  input_file_id uuid not null references public.files(id) on delete cascade,
  output_file_id uuid references public.files(id) on delete set null,
  input_format text not null,
  output_format text not null,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'failed')),
  error_message text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

comment on table public.conversions is 'Tracks document conversion jobs. output_file_id is null until the conversion completes successfully.';

create index if not exists idx_conversions_user_id on public.conversions(user_id);
create index if not exists idx_conversions_created_at on public.conversions(created_at desc);
create index if not exists idx_conversions_status on public.conversions(status);
create index if not exists idx_conversions_input_file on public.conversions(input_file_id);

-- --- Row Level Security -----------------------------------------

alter table public.conversions enable row level security;

drop policy if exists "Users can view their own conversions" on public.conversions;
create policy "Users can view their own conversions"
  on public.conversions for select
  using (auth.uid() = user_id);

drop policy if exists "Users can insert their own conversions" on public.conversions;
create policy "Users can insert their own conversions"
  on public.conversions for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users can update their own conversions" on public.conversions;
create policy "Users can update their own conversions"
  on public.conversions for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- No delete policy — conversion history is intentionally permanent
-- (deleting the underlying files via the Vault is still possible;
-- output_file_id will simply go null via ON DELETE SET NULL).
