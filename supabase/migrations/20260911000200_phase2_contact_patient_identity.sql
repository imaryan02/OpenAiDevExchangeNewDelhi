-- Phase: 2.2a — Contact and patient identity
-- Requirements: PAT-01, PAT-02, RET-01, TEN-01
-- Apply after 20260911000100_phase2_scheduling.sql.
-- Recovery: additive schema only. Archive records; do not delete patient/contact history.

begin;

create table public.contacts (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    display_name text not null check (char_length(trim(display_name)) between 1 and 160),
    name_source text not null default 'STATED' check (name_source in ('STATED', 'STAFF_ENTERED', 'IMPORTED')),
    status text not null default 'ACTIVE' check (status in ('ACTIVE', 'ARCHIVED')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, id)
);

create table public.contact_phones (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    contact_id uuid not null,
    phone_e164 text not null check (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
    status text not null default 'ACTIVE' check (status in ('ACTIVE', 'DISABLED', 'REASSIGNED')),
    last_verified_at timestamptz,
    version integer not null default 1 check (version > 0),
    messaging_consent boolean not null default false,
    consent_recorded_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint contact_phones_contact_tenant_fk
        foreign key (organization_id, contact_id)
        references public.contacts (organization_id, id) on delete restrict,
    constraint contact_phones_consent_timestamp_check
        check ((messaging_consent = false and consent_recorded_at is null) or (messaging_consent = true and consent_recorded_at is not null)),
    unique (organization_id, id)
);

create unique index contact_phones_one_active_phone_per_tenant_idx
    on public.contact_phones (organization_id, phone_e164) where status = 'ACTIVE';
create index contact_phones_contact_active_idx
    on public.contact_phones (organization_id, contact_id) where status = 'ACTIVE';

create table public.patients (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    display_name text not null check (char_length(trim(display_name)) between 1 and 160),
    disambiguation text not null default '' check (char_length(disambiguation) <= 160),
    status text not null default 'ACTIVE' check (status in ('ACTIVE', 'ARCHIVED')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, id)
);

create table public.patient_contacts (
    organization_id uuid not null references public.organizations(id) on delete restrict,
    patient_id uuid not null,
    contact_id uuid not null,
    relationship text not null check (char_length(trim(relationship)) between 1 and 80),
    relationship_status text not null default 'RECORDED' check (relationship_status in ('RECORDED', 'REVOKED')),
    recorded_by_auth_user_id uuid references auth.users(id) on delete set null,
    recorded_at timestamptz not null default now(),
    revoked_at timestamptz,
    constraint patient_contacts_patient_tenant_fk
        foreign key (organization_id, patient_id)
        references public.patients (organization_id, id) on delete restrict,
    constraint patient_contacts_contact_tenant_fk
        foreign key (organization_id, contact_id)
        references public.contacts (organization_id, id) on delete restrict,
    constraint patient_contacts_revocation_check
        check ((relationship_status = 'RECORDED' and revoked_at is null) or (relationship_status = 'REVOKED' and revoked_at is not null)),
    primary key (organization_id, patient_id, contact_id)
);

create index patients_organization_active_name_idx
    on public.patients (organization_id, display_name) where status = 'ACTIVE';
create index patient_contacts_contact_active_idx
    on public.patient_contacts (organization_id, contact_id) where relationship_status = 'RECORDED';

create or replace function private.is_org_booking_staff(target_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.organization_users as membership
        where membership.organization_id = target_organization_id
          and membership.auth_user_id = (select auth.uid())
          and membership.active = true
          and membership.role in ('ORG_ADMIN', 'RECEPTIONIST')
    );
$$;

revoke all on function private.is_org_booking_staff(uuid) from public;
grant execute on function private.is_org_booking_staff(uuid) to authenticated;

drop trigger if exists contacts_set_updated_at on public.contacts;
create trigger contacts_set_updated_at before update on public.contacts
for each row execute function private.set_updated_at();
drop trigger if exists contact_phones_set_updated_at on public.contact_phones;
create trigger contact_phones_set_updated_at before update on public.contact_phones
for each row execute function private.set_updated_at();
drop trigger if exists patients_set_updated_at on public.patients;
create trigger patients_set_updated_at before update on public.patients
for each row execute function private.set_updated_at();

alter table public.contacts enable row level security;
alter table public.contact_phones enable row level security;
alter table public.patients enable row level security;
alter table public.patient_contacts enable row level security;

create policy contacts_booking_staff_select on public.contacts for select to authenticated
using ((select private.is_org_booking_staff(organization_id)));
create policy contacts_booking_staff_write on public.contacts for all to authenticated
using ((select private.is_org_booking_staff(organization_id)))
with check ((select private.is_org_booking_staff(organization_id)));
create policy contact_phones_booking_staff_select on public.contact_phones for select to authenticated
using ((select private.is_org_booking_staff(organization_id)));
create policy contact_phones_booking_staff_write on public.contact_phones for all to authenticated
using ((select private.is_org_booking_staff(organization_id)))
with check ((select private.is_org_booking_staff(organization_id)));
create policy patients_booking_staff_select on public.patients for select to authenticated
using ((select private.is_org_booking_staff(organization_id)));
create policy patients_booking_staff_write on public.patients for all to authenticated
using ((select private.is_org_booking_staff(organization_id)))
with check ((select private.is_org_booking_staff(organization_id)));
create policy patient_contacts_booking_staff_select on public.patient_contacts for select to authenticated
using ((select private.is_org_booking_staff(organization_id)));
create policy patient_contacts_booking_staff_write on public.patient_contacts for all to authenticated
using ((select private.is_org_booking_staff(organization_id)))
with check ((select private.is_org_booking_staff(organization_id)));

commit;
