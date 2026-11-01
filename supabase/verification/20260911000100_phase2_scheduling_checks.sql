-- Run after 20260911000100_phase2_scheduling.sql. Read-only single-result verification.
with expected(table_name) as (
  values ('schedule_rules'), ('schedule_exceptions'), ('appointment_sessions'), ('appointment_slots')
)
select jsonb_build_object(
  'tables', (
    select jsonb_agg(jsonb_build_object('table_name', c.relname, 'rls_enabled', c.relrowsecurity) order by c.relname)
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r' and c.relname in (select table_name from expected)
  ),
  'summary', jsonb_build_object(
    'tables_found', (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind = 'r' and c.relname in (select table_name from expected)),
    'all_rls_enabled', (select coalesce(bool_and(c.relrowsecurity), false) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind = 'r' and c.relname in (select table_name from expected)),
    'doctor_time_exclusion_present', (select exists (select 1 from pg_constraint where conname = 'appointment_sessions_doctor_time_exclusion'))
  ),
  'policies', (
    select jsonb_agg(jsonb_build_object('table_name', tablename, 'policy_name', policyname, 'command', cmd) order by tablename, policyname)
    from pg_policies where schemaname = 'public' and tablename in (select table_name from expected)
  )
) as phase_2_scheduling_verification;
