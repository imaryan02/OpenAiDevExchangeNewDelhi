select
  to_regclass('public.voice_observability_usage') is not null as usage_table_exists,
  exists (
    select 1 from pg_indexes
     where schemaname = 'public'
       and indexname = 'voice_observability_usage_call_idx'
  ) as usage_call_index_exists,
  coalesce((
    select relrowsecurity from pg_class
     where oid = 'public.voice_observability_usage'::regclass
  ), false) as usage_rls_enabled,
  exists (
    select 1 from pg_policies
     where schemaname = 'public'
       and tablename = 'voice_observability_usage'
       and policyname = 'voice_observability_usage_booking_staff'
       and cmd = 'SELECT'
  ) as usage_staff_policy_exists;
