-- Run after 20260911000400_phase2_transactional_booking.sql. Read-only single-result verification.
select jsonb_build_object(
  'summary', jsonb_build_object(
    'idempotency_table_present', (select exists (select 1 from information_schema.tables where table_schema='public' and table_name='idempotency_records')),
    'idempotency_rls_enabled', (select coalesce(c.relrowsecurity, false) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='idempotency_records'),
    'hold_function_present', (select exists (select 1 from information_schema.routines where routine_schema='public' and routine_name='create_simulated_appointment_hold')),
    'confirmation_function_present', (select exists (select 1 from information_schema.routines where routine_schema='public' and routine_name='confirm_simulated_appointment')),
    'expiry_function_present', (select exists (select 1 from information_schema.routines where routine_schema='public' and routine_name='expire_simulated_appointment_holds')),
    'contact_route_guard_present', (select exists (select 1 from information_schema.routines where routine_schema='private' and routine_name='enforce_appointment_contact_route'))
  )
) as phase_2_transactional_booking_verification;
