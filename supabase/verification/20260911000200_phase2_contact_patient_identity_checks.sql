-- Run after 20260911000200_phase2_contact_patient_identity.sql. Read-only single-result verification.
with expected(table_name) as (
  values ('contacts'), ('contact_phones'), ('patients'), ('patient_contacts')
)
select jsonb_build_object(
  'summary', jsonb_build_object(
    'tables_found', (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind = 'r' and c.relname in (select table_name from expected)),
    'all_rls_enabled', (select coalesce(bool_and(c.relrowsecurity), false) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind = 'r' and c.relname in (select table_name from expected)),
    'booking_staff_helper_present', (select exists (select 1 from information_schema.routines where routine_schema = 'private' and routine_name = 'is_org_booking_staff')),
    'active_phone_uniqueness_present', (select exists (select 1 from pg_indexes where schemaname = 'public' and indexname = 'contact_phones_one_active_phone_per_tenant_idx'))
  ),
  'tables', (select jsonb_agg(jsonb_build_object('table_name', c.relname, 'rls_enabled', c.relrowsecurity) order by c.relname) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind = 'r' and c.relname in (select table_name from expected)),
  'policies', (select jsonb_agg(jsonb_build_object('table_name', tablename, 'policy_name', policyname, 'command', cmd) order by tablename, policyname) from pg_policies where schemaname = 'public' and tablename in (select table_name from expected))
) as phase_2_contact_patient_verification;
