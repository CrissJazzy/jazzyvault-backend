-- ============================================================
-- JazzyVault — Migration 005: Name conversions->files foreign keys
-- ============================================================
-- The `conversions` table (Phase 4) has TWO foreign keys pointing at
-- `files`: input_file_id and output_file_id. Postgres auto-generates
-- a name for unnamed foreign keys, but having two FKs to the same
-- target table is exactly the case PostgREST's resource embedding
-- needs a named constraint to disambiguate (see
-- https://docs.postgrest.org/en/v12/references/api/resource_embedding.html).
--
-- This migration renames the existing (auto-generated) constraints to
-- explicit, predictable names, which the new GET /convert/history
-- endpoint (Phase 5) relies on:
--   files!conversions_input_file_fkey(file_name, file_size)
--
-- Safe to run on a database that already has migration 003 applied —
-- this only renames existing constraints, it doesn't touch data.
-- ============================================================

do $$
declare
  input_fkey_name text;
  output_fkey_name text;
begin
  -- Find the current (likely auto-generated) constraint name for each FK.
  select conname into input_fkey_name
  from pg_constraint
  where conrelid = 'public.conversions'::regclass
    and contype = 'f'
    and conkey = (
      select array_agg(attnum order by attnum)
      from pg_attribute
      where attrelid = 'public.conversions'::regclass
        and attname = 'input_file_id'
    );

  select conname into output_fkey_name
  from pg_constraint
  where conrelid = 'public.conversions'::regclass
    and contype = 'f'
    and conkey = (
      select array_agg(attnum order by attnum)
      from pg_attribute
      where attrelid = 'public.conversions'::regclass
        and attname = 'output_file_id'
    );

  if input_fkey_name is not null and input_fkey_name <> 'conversions_input_file_fkey' then
    execute format(
      'alter table public.conversions rename constraint %I to conversions_input_file_fkey',
      input_fkey_name
    );
  end if;

  if output_fkey_name is not null and output_fkey_name <> 'conversions_output_file_fkey' then
    execute format(
      'alter table public.conversions rename constraint %I to conversions_output_file_fkey',
      output_fkey_name
    );
  end if;
end $$;
