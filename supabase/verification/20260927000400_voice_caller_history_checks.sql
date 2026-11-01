-- Does not return any phone numbers.
select exists (select 1 from information_schema.columns
  where table_schema='public' and table_name='voice_observability_calls'
    and column_name='caller_number') as caller_column_exists,
  to_regclass('public.voice_calls_org_caller_started_idx') is not null as caller_index_exists,
  (select relrowsecurity from pg_class
    where oid='public.voice_observability_calls'::regclass) as calls_rls_enabled,
  exists (select 1 from pg_policies where schemaname='public'
    and tablename='voice_observability_calls'
    and policyname='voice_observability_calls_booking_staff') as staff_policy_exists;
select count(*) as total_calls,
  count(caller_number) as calls_with_number,
  count(*) filter (where caller_number_source='RUNTIME_LINK') as recovered_calls,
  (select count(*) from (select organization_id, caller_number
     from public.voice_observability_calls where caller_number is not null
     group by organization_id, caller_number having count(*) > 1) repeat_groups)
    as repeat_caller_groups
from public.voice_observability_calls;
