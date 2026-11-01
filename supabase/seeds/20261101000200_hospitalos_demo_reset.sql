-- Optional owner-run demo reset. Deletes only HospitalOS case/request/event/hold data.
-- Keeps the three synthetic facility listings and their resource settings.
-- Do not run during an active demonstration.
begin;

truncate table public.hospitalos_events, public.hospitalos_holds,
    public.hospitalos_requests, public.hospitalos_cases restart identity;

commit;
