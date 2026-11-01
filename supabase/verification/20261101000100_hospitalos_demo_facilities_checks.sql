-- Read-only verification after the HospitalOS Phase 1 migration and optional demo seed.
select to_regclass('public.hospitalos_facilities') as facility_table;
select relrowsecurity as rls_enabled
from pg_class where oid='public.hospitalos_facilities'::regclass;
select policyname, cmd from pg_policies
where schemaname='public' and tablename='hospitalos_facilities'
order by policyname;
select slug, synthetic, receiving_enabled, organization_id is not null as connected
from public.hospitalos_facilities order by slug;
