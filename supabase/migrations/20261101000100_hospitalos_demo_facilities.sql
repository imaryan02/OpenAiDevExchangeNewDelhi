-- HospitalOS Phase 1: isolated synthetic facility resource records.
-- Apply once to the intended demo database after checking the existing migration ledger.
-- Recovery: disable the HospitalOS routes; retain rows for investigation rather than dropping data.
begin;

create table if not exists public.hospitalos_facilities (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique check (slug ~ '^[a-z0-9-]{3,80}$'),
    organization_id uuid references public.organizations(id) on delete restrict,
    location_id uuid,
    name text not null check (length(trim(name)) between 1 and 160),
    area text not null check (length(trim(area)) between 1 and 120),
    address text not null default '' check (length(address) <= 300),
    latitude numeric(9,6) not null check (latitude between -90 and 90),
    longitude numeric(9,6) not null check (longitude between -180 and 180),
    cost_category text not null check (cost_category in ('GOVERNMENT','CHARITABLE','PRIVATE')),
    emergency_open boolean not null default false,
    ed_bays_ready smallint not null default 0 check (ed_bays_ready between 0 and 1000),
    icu_beds_ready smallint not null default 0 check (icu_beds_ready between 0 and 1000),
    ventilators_ready smallint not null default 0 check (ventilators_ready between 0 and 1000),
    ct_available boolean not null default false,
    trauma_available boolean not null default false,
    pediatric_available boolean not null default false,
    obstetric_available boolean not null default false,
    receiving_enabled boolean not null default false,
    synthetic boolean not null default true check (synthetic),
    version integer not null default 1 check (version > 0),
    verified_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    updated_by uuid,
    constraint hospitalos_facility_binding_check
        check ((organization_id is null and location_id is null and not receiving_enabled)
            or (organization_id is not null and location_id is not null)),
    constraint hospitalos_facility_location_fk
        foreign key (organization_id, location_id)
        references public.locations(organization_id, id) on delete restrict
);

create index if not exists hospitalos_facilities_org_location_idx
    on public.hospitalos_facilities (organization_id, location_id)
    where organization_id is not null;

alter table public.hospitalos_facilities enable row level security;

create policy hospitalos_facilities_staff_read on public.hospitalos_facilities
    for select to authenticated
    using (organization_id is not null and private.is_org_member(organization_id));

create policy hospitalos_facilities_admin_update on public.hospitalos_facilities
    for update to authenticated
    using (organization_id is not null and private.is_org_admin(organization_id))
    with check (organization_id is not null and private.is_org_admin(organization_id));

revoke all on public.hospitalos_facilities from anon, authenticated;
grant select, update on public.hospitalos_facilities to authenticated;

commit;
