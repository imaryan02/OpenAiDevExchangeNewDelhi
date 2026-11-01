-- Move the Geeta Medicine demo from Nepal defaults to India defaults.
-- Existing appointment and payment rows belong to this synthetic demo, so their
-- simulated currency snapshots are relabelled with the rest of the demo data.

begin;

alter table public.doctor_assignments alter column currency set default 'INR';
alter table public.appointments alter column currency set default 'INR';
alter table public.payment_attempts alter column currency set default 'INR';

with target_organizations as (
    select id from public.organizations where name = 'Geeta Medicine'
)
update public.organizations
set timezone = 'Asia/Kolkata'
where id in (select id from target_organizations);

with target_organizations as (
    select id from public.organizations where name = 'Geeta Medicine'
)
update public.locations
set timezone = 'Asia/Kolkata',
    address = case when address = 'Birgunj, Nepal' then 'India' else address end
where organization_id in (select id from target_organizations);

with target_organizations as (
    select id from public.organizations where name = 'Geeta Medicine'
)
update public.appointment_sessions session
set timezone = 'Asia/Kolkata'
where session.organization_id in (select id from target_organizations)
  and session.timezone = 'Asia/Kathmandu';

with target_organizations as (
    select id from public.organizations where name = 'Geeta Medicine'
)
update public.doctor_assignments
set currency = 'INR'
where organization_id in (select id from target_organizations)
  and currency = 'NPR';

with target_organizations as (
    select id from public.organizations where name = 'Geeta Medicine'
)
update public.appointments
set currency = 'INR',
    quote_snapshot = case
        when quote_snapshot ? 'currency'
        then jsonb_set(quote_snapshot, '{currency}', '"INR"'::jsonb)
        else quote_snapshot
    end
where organization_id in (select id from target_organizations)
  and currency = 'NPR';

with target_organizations as (
    select id from public.organizations where name = 'Geeta Medicine'
)
update public.payment_attempts
set currency = 'INR'
where organization_id in (select id from target_organizations)
  and currency = 'NPR';

-- Demo caller records used Nepal prefixes. Convert them without violating the
-- active phone uniqueness constraint if the equivalent Indian number exists.
with target_organizations as (
    select id from public.organizations where name = 'Geeta Medicine'
)
update public.contact_phones phone
set phone_e164 = '+91' || substring(phone.phone_e164 from 5),
    version = phone.version + 1
where phone.organization_id in (select id from target_organizations)
  and phone.phone_e164 like '+977%'
  and not exists (
      select 1
      from public.contact_phones existing
      where existing.organization_id = phone.organization_id
        and existing.phone_e164 = '+91' || substring(phone.phone_e164 from 5)
        and existing.status = 'ACTIVE'
  );

commit;

select jsonb_build_object(
    'india_localization', jsonb_build_object(
        'timezone', 'Asia/Kolkata',
        'currency', 'INR',
        'phone_prefix', '+91'
    )
) as verification;
