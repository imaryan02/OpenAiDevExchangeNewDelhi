-- Read-only; safe even when manual SQL application has not created a ledger.
select
  to_regclass('supabase_migrations.schema_migrations') is not null
    as migration_ledger_exists,
  to_regprocedure('private.is_org_booking_staff(uuid)') is not null
    as booking_staff_authorization_function_exists,
  exists (
    select 1 from pg_constraint
    where conrelid = to_regclass('public.schedule_rules')
      and conname = 'schedule_rules_session_windows_only_check'
  ) as session_windows_constraint_exists,
  (
    select pg_get_constraintdef(oid) from pg_constraint
    where conrelid = to_regclass('public.schedule_rules')
      and conname = 'schedule_rules_session_windows_only_check'
  ) as session_windows_constraint_definition;
