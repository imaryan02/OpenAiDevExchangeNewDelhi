-- Read-only verification; expected: nine tables, all RLS enabled, all read policies.
select c.relname, c.relrowsecurity,
       exists(select 1 from pg_policies p where p.schemaname='public'
              and p.tablename=c.relname and p.policyname='personal_owner_read') as owner_policy
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relname in (
    'personal_agent_profiles','personal_agent_tasks','personal_agent_followups',
    'personal_agent_calls','personal_agent_attempts','personal_agent_messages',
    'personal_agent_memory','personal_agent_events','personal_agent_tool_results'
) order by c.relname;
select indexname from pg_indexes where schemaname='public'
and tablename like 'personal_agent_%' order by indexname;

-- All outbound FK targets must be other personal tables or auth.users.
-- Expected: zero rows. No new personal table depends on any clinic table.
select c.conname, source.relname as source_table,
       target_ns.nspname as target_schema, target.relname as target_table
from pg_constraint c
join pg_class source on source.oid=c.conrelid
join pg_namespace source_ns on source_ns.oid=source.relnamespace
join pg_class target on target.oid=c.confrelid
join pg_namespace target_ns on target_ns.oid=target.relnamespace
where c.contype='f' and source_ns.nspname='public'
  and source.relname like 'personal_agent_%'
  and not (target_ns.nspname='public' and target.relname like 'personal_agent_%')
  and not (target_ns.nspname='auth' and target.relname='users');

-- Expected for every personal table: anon_read=false, client_write=false.
-- Includes privileges inherited from role membership, rather than ACL rows only.
select c.relname,
       has_table_privilege('anon',c.oid,'SELECT') as anon_read,
       has_table_privilege('authenticated',c.oid,'INSERT')
         or has_table_privilege('authenticated',c.oid,'UPDATE')
         or has_table_privilege('authenticated',c.oid,'DELETE')
         or has_table_privilege('anon',c.oid,'INSERT')
         or has_table_privilege('anon',c.oid,'UPDATE')
         or has_table_privilege('anon',c.oid,'DELETE') as client_write
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind='r' and c.relname like 'personal_agent_%'
order by c.relname;
