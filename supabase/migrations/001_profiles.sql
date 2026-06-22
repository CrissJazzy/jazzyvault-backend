-- ============================================================
-- JazzyVault — Migration 001: Profiles
-- ============================================================
-- Creates the `profiles` table (1:1 with auth.users), enables
-- Row Level Security, and wires up a trigger so a profile row
-- is automatically created whenever a new user registers via
-- Supabase Auth.
-- ============================================================

-- --- Table ---------------------------------------------------

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text,
  avatar_url text,
  storage_used_bytes bigint not null default 0,
  storage_limit_bytes bigint not null default 1073741824, -- 1 GB default (free tier)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.profiles is 'One row per authenticated user. Created automatically on signup via handle_new_user trigger.';

-- --- updated_at auto-touch ------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at
  before update on public.profiles
  for each row
  execute function public.set_updated_at();

-- --- Auto-create profile on signup -----------------------------
-- Fires on every new row in auth.users (i.e. every registration,
-- including OAuth providers if added later).

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, full_name)
  values (
    new.id,
    new.email,
    new.raw_user_meta_data->>'full_name'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();

-- --- Row Level Security -----------------------------------------

alter table public.profiles enable row level security;

drop policy if exists "Users can view their own profile" on public.profiles;
create policy "Users can view their own profile"
  on public.profiles for select
  using (auth.uid() = id);

drop policy if exists "Users can update their own profile" on public.profiles;
create policy "Users can update their own profile"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- No insert/delete policies for regular users — profile rows are
-- created exclusively by the handle_new_user trigger (security definer)
-- and deleted via the auth.users cascade.

-- --- Index --------------------------------------------------------

create index if not exists idx_profiles_email on public.profiles(email);
