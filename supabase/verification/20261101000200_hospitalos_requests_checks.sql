-- Read-only Phase 2 checks. Never print tracking-token hashes.
select table_name, row_security
from information_schema.tables t
join (
    select c.relname, c.relrowsecurity as row_security
    from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public'
) p on p.relname=t.table_name
where t.table_schema='public' and t.table_name in
  ('hospitalos_cases','hospitalos_requests','hospitalos_holds','hospitalos_events')
order by table_name;

select status, count(*) from public.hospitalos_requests group by status order by status;
select event_type, count(*) from public.hospitalos_events group by event_type order by event_type;
select status, count(*) from public.hospitalos_holds group by status order by status;

-- A request may have at most one hold by schema uniqueness.
select request_id, count(*) from public.hospitalos_holds
group by request_id having count(*) > 1;
