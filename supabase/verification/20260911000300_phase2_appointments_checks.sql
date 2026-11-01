-- Run after 20260911000300_phase2_appointments.sql. Read-only single-result verification.
with expected(table_name) as (values ('appointments'), ('appointment_contact_permissions'), ('verification_challenges'), ('payment_attempts'))
select jsonb_build_object(
  'summary', jsonb_build_object(
    'tables_found', (select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and c.relname in (select table_name from expected)),
    'all_rls_enabled', (select coalesce(bool_and(c.relrowsecurity), false) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and c.relname in (select table_name from expected)),
    'exact_slot_uniqueness_present', (select exists (select 1 from pg_indexes where schemaname='public' and indexname='appointments_active_exact_slot_idx')),
    'token_uniqueness_present', (select exists (select 1 from pg_indexes where schemaname='public' and indexname='appointments_session_token_idx')),
    'session_shape_guard_present', (select exists (select 1 from information_schema.routines where routine_schema='private' and routine_name='enforce_appointment_session_shape'))
  ),
  'tables', (select jsonb_agg(jsonb_build_object('table_name', c.relname, 'rls_enabled', c.relrowsecurity) order by c.relname) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and c.relname in (select table_name from expected)),
  'policies', (select jsonb_agg(jsonb_build_object('table_name', tablename, 'policy_name', policyname, 'command', cmd) order by tablename, policyname) from pg_policies where schemaname='public' and tablename in (select table_name from expected))
) as phase_2_appointments_verification;
