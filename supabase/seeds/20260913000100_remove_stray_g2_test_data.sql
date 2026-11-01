-- Remove only synthetic tenants left by backend/tests/test_g2_database.py.
-- Keeps unrelated organizations and transfers their test user's membership to
-- the configured Geeta Medicine demo organization before deletion.

begin;

create temporary table cleanup_g2_organizations on commit drop as
select id
from public.organizations
where name like 'G2 Test %';

create temporary table cleanup_g2_doctors on commit drop as
select distinct assignment.doctor_id as id
from public.doctor_assignments assignment
join cleanup_g2_organizations test_org on test_org.id = assignment.organization_id;

-- Azure VOICE_ORGANIZATION_ID. Stop if the intended demo tenant is absent.
do $$
begin
    if not exists (
        select 1 from public.organizations
        where id = 'c562e817-bfae-4428-904d-15ac84b9acd7'::uuid
          and name = 'Geeta Medicine'
    ) then
        raise exception 'Configured Geeta Medicine organization was not found; cleanup cancelled';
    end if;
end;
$$;

insert into public.organization_users (organization_id, auth_user_id, role, active)
select distinct 'c562e817-bfae-4428-904d-15ac84b9acd7'::uuid,
       membership.auth_user_id,
       'ORG_ADMIN',
       true
from public.organization_users membership
join cleanup_g2_organizations test_org on test_org.id = membership.organization_id
on conflict (organization_id, auth_user_id)
do update set role = 'ORG_ADMIN', active = true;

delete from public.voice_operation_records where organization_id in (select id from cleanup_g2_organizations);
delete from public.voice_call_sessions where organization_id in (select id from cleanup_g2_organizations);
delete from public.verification_challenges where organization_id in (select id from cleanup_g2_organizations);
delete from public.payment_attempts where organization_id in (select id from cleanup_g2_organizations);
delete from public.appointment_contact_permissions where organization_id in (select id from cleanup_g2_organizations);
delete from public.outbox_jobs where organization_id in (select id from cleanup_g2_organizations);
delete from public.idempotency_records where organization_id in (select id from cleanup_g2_organizations);
delete from public.appointments where organization_id in (select id from cleanup_g2_organizations);
delete from public.appointment_slots where organization_id in (select id from cleanup_g2_organizations);
delete from public.appointment_sessions where organization_id in (select id from cleanup_g2_organizations);
delete from public.schedule_exceptions where organization_id in (select id from cleanup_g2_organizations);
delete from public.schedule_rules where organization_id in (select id from cleanup_g2_organizations);
delete from public.patient_contacts where organization_id in (select id from cleanup_g2_organizations);
delete from public.contact_phones where organization_id in (select id from cleanup_g2_organizations);
delete from public.patients where organization_id in (select id from cleanup_g2_organizations);
delete from public.contacts where organization_id in (select id from cleanup_g2_organizations);
delete from public.audit_events where organization_id in (select id from cleanup_g2_organizations);
delete from public.inbox_events where organization_id in (select id from cleanup_g2_organizations);
delete from public.doctor_assignments where organization_id in (select id from cleanup_g2_organizations);
delete from public.organization_users where organization_id in (select id from cleanup_g2_organizations);
delete from public.departments where organization_id in (select id from cleanup_g2_organizations);
delete from public.locations where organization_id in (select id from cleanup_g2_organizations);
delete from public.organizations where id in (select id from cleanup_g2_organizations);

delete from public.doctors doctor
where doctor.id in (select id from cleanup_g2_doctors)
  and doctor.canonical_name = 'Dr G2 Test'
  and not exists (
      select 1 from public.doctor_assignments assignment where assignment.doctor_id = doctor.id
  );

commit;

select count(*) as remaining_g2_organizations
from public.organizations
where name like 'G2 Test %';
