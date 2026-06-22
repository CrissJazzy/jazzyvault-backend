-- ============================================================
-- JazzyVault — Migration 002: Files & Storage
-- ============================================================
-- Creates the `files` table (the Vault), enables Row Level
-- Security, and sets up Storage bucket policies so users can
-- only access their own files.
-- ============================================================

-- --- Table ---------------------------------------------------

create table if not exists public.files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  file_name text not null,
  storage_path text not null unique,
  file_url text not null,
  file_size bigint not null,
  file_type text not null,
  created_at timestamptz not null default now()
);

comment on table public.files is 'User-uploaded files in the Vault. storage_path maps to the Supabase Storage object key.';

create index if not exists idx_files_user_id on public.files(user_id);
create index if not exists idx_files_created_at on public.files(created_at desc);
create index if not exists idx_files_file_name on public.files using gin (to_tsvector('english', file_name));

-- --- Row Level Security -----------------------------------------

alter table public.files enable row level security;

drop policy if exists "Users can view their own files" on public.files;
create policy "Users can view their own files"
  on public.files for select
  using (auth.uid() = user_id);

drop policy if exists "Users can insert their own files" on public.files;
create policy "Users can insert their own files"
  on public.files for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users can delete their own files" on public.files;
create policy "Users can delete their own files"
  on public.files for delete
  using (auth.uid() = user_id);

-- No update policy — files are immutable once uploaded. Conversions
-- (Phase 4) create new file rows rather than mutating existing ones.

-- --- Storage usage tracking ---------------------------------------
-- Keeps profiles.storage_used_bytes in sync automatically whenever
-- a file is inserted or deleted, so the dashboard never has to
-- compute SUM(file_size) on every page load.

create or replace function public.handle_file_insert()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.profiles
  set storage_used_bytes = storage_used_bytes + new.file_size
  where id = new.user_id;
  return new;
end;
$$;

drop trigger if exists on_file_insert on public.files;
create trigger on_file_insert
  after insert on public.files
  for each row
  execute function public.handle_file_insert();

create or replace function public.handle_file_delete()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.profiles
  set storage_used_bytes = greatest(0, storage_used_bytes - old.file_size)
  where id = old.user_id;
  return old;
end;
$$;

drop trigger if exists on_file_delete on public.files;
create trigger on_file_delete
  after delete on public.files
  for each row
  execute function public.handle_file_delete();

-- ============================================================
-- Storage bucket setup
-- ============================================================
-- The bucket itself must be created via Supabase Dashboard or the
-- Storage API (SQL alone cannot create buckets in all Supabase
-- versions) — see README "Phase 3 — Required Supabase Setup" for
-- the dashboard steps. The policies below assume a bucket named
-- 'jazzyvault-files' with this path convention:
--   {user_id}/{uuid}-{original_filename}
-- which lets RLS scope access using the first path segment.

insert into storage.buckets (id, name, public)
values ('jazzyvault-files', 'jazzyvault-files', false)
on conflict (id) do nothing;

drop policy if exists "Users can upload to their own folder" on storage.objects;
create policy "Users can upload to their own folder"
  on storage.objects for insert
  with check (
    bucket_id = 'jazzyvault-files'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "Users can view their own files" on storage.objects;
create policy "Users can view their own files"
  on storage.objects for select
  using (
    bucket_id = 'jazzyvault-files'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "Users can delete their own files" on storage.objects;
create policy "Users can delete their own files"
  on storage.objects for delete
  using (
    bucket_id = 'jazzyvault-files'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
