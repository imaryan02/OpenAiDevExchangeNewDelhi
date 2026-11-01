-- Run after 20260927000100_voice_observability.sql in the intended Supabase project.
select
  to_regclass('public.voice_observability_calls') is not null as calls_table_exists,
  to_regclass('public.voice_observability_events') is not null as events_table_exists,
  exists (
    select 1 from pg_indexes
    where schemaname = 'public' and indexname = 'voice_observability_calls_org_started_idx'
  ) as calls_tenant_index_exists,
  exists (
    select 1 from pg_indexes
    where schemaname = 'public' and indexname = 'voice_observability_events_call_sequence_idx'
  ) as events_timeline_index_exists,
  coalesce((select relrowsecurity from pg_class where oid = 'public.voice_observability_calls'::regclass), false)
    as calls_rls_enabled,
  coalesce((select relrowsecurity from pg_class where oid = 'public.voice_observability_events'::regclass), false)
    as events_rls_enabled,
  exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'voice_observability_calls'
      and policyname = 'voice_observability_calls_booking_staff'
  ) as calls_staff_policy_exists,
  exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'voice_observability_events'
      and policyname = 'voice_observability_events_booking_staff'
  ) as events_staff_policy_exists;
