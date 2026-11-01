-- Run after 20260910000100_phase1_tenant_foundation.sql.
-- Read-only: returns one JSON result containing every Phase 1 verification check.

with
expected_tables(table_name) as (
  values
    ('organizations'), ('locations'), ('departments'), ('doctors'),
    ('organization_users'), ('doctor_assignments'), ('audit_events')
),
expected_functions(routine_schema, routine_name) as (
  values
    ('public', 'create_organization_with_admin'),
    ('private', 'is_org_member'),
    ('private', 'is_org_admin'),
    ('private', 'set_updated_at'),
    ('private', 'prevent_audit_mutation')
)
select jsonb_build_object(
  'summary', jsonb_build_object(
    'expected_tables', 7,
    'tables_found', (
      select count(*)
      from expected_tables e
      join pg_class c on c.relname = e.table_name and c.relkind = 'r'
      join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'public'
    ),
    'all_rls_enabled', (
      select coalesce(bool_and(c.relrowsecurity), false)
      from expected_tables e
      join pg_class c on c.relname = e.table_name and c.relkind = 'r'
      join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'public'
    ),
    'expected_functions', 5,
    'functions_found', (
      select count(*)
      from expected_functions e
      join information_schema.routines r
        on r.routine_schema = e.routine_schema and r.routine_name = e.routine_name
    )
  ),
  'tables', coalesce((
    select jsonb_agg(row_data order by row_data ->> 'table_name')
    from (
      select jsonb_build_object('table_name', c.relname, 'rls_enabled', c.relrowsecurity) as row_data
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'public' and c.relkind = 'r'
        and c.relname in (select table_name from expected_tables)
    ) rows
  ), '[]'::jsonb),
  'policies', coalesce((
    select jsonb_agg(row_data order by row_data ->> 'table_name', row_data ->> 'policy_name')
    from (
      select jsonb_build_object('table_name', tablename, 'policy_name', policyname, 'command', cmd, 'roles', roles) as row_data
      from pg_policies
      where schemaname = 'public' and tablename in (select table_name from expected_tables)
    ) rows
  ), '[]'::jsonb),
  'functions', coalesce((
    select jsonb_agg(row_data order by row_data ->> 'schema', row_data ->> 'function_name')
    from (
      select jsonb_build_object('schema', routine_schema, 'function_name', routine_name, 'security_type', security_type) as row_data
      from information_schema.routines
      where (routine_schema, routine_name) in (select routine_schema, routine_name from expected_functions)
    ) rows
  ), '[]'::jsonb),
  'indexes', coalesce((
    select jsonb_agg(row_data order by row_data ->> 'table_name', row_data ->> 'index_name')
    from (
      select jsonb_build_object('table_name', tablename, 'index_name', indexname) as row_data
      from pg_indexes
      where schemaname = 'public' and tablename in (select table_name from expected_tables)
    ) rows
  ), '[]'::jsonb)
) as phase_1_verification;
