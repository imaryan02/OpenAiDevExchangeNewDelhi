-- Read-only verification for 20260911000500_phase2_cancellation_outbox.sql.
select jsonb_build_object(
  'summary', jsonb_build_object(
    'outbox_table_present', (select exists (select 1 from information_schema.tables where table_schema='public' and table_name='outbox_jobs')),
    'outbox_rls_enabled', (select coalesce(c.relrowsecurity, false) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='outbox_jobs'),
    'cancel_function_present', (select exists (select 1 from information_schema.routines where routine_schema='public' and routine_name='cancel_appointment')),
    'outbox_policy_present', (select exists (select 1 from pg_policies where schemaname='public' and tablename='outbox_jobs' and policyname='outbox_jobs_admin_select'))
  )
) as phase_2_cancellation_outbox_verification;
