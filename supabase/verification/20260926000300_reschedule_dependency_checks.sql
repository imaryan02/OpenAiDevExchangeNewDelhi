-- Read-only: object existence alone does not establish executable dependencies.
select p.proname as function_name,
       pg_get_function_identity_arguments(p.oid) as arguments,
       p.prosrc ~ 'private\.' as references_private_schema,
       to_regnamespace('private') is not null as private_schema_exists,
       pg_get_functiondef(p.oid) as definition
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname in (
  'reschedule_appointment', 'enforce_rescheduled_appointment_integrity',
  'copy_rescheduled_payment_attempt'
)
order by p.proname;
