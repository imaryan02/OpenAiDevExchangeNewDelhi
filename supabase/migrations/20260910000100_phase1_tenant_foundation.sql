-- Phase: 1 — Foundation, tenancy and authenticated skeleton
-- Requirements: TEN-01, TEN-02, IAM-01, DOC-01, SEC-01, OBS-01
-- Apply once in the target Supabase SQL editor as project database owner.
-- Validate afterwards with supabase/verification/20260910000100_phase1_tenant_foundation_checks.sql.
-- Recovery: additive migration; do not drop these tables in a shared environment.

begin;

create extension if not exists pgcrypto;
create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to authenticated;

create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null check (char_length(trim(name)) between 1 and 160),
    organization_type text not null check (organization_type in ('CLINIC', 'HOSPITAL')),
    timezone text not null,
    status text not null default 'DRAFT' check (status in ('DRAFT', 'ACTIVE', 'SUSPENDED')),
    policy_version integer not null default 1 check (policy_version > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.locations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    name text not null check (char_length(trim(name)) between 1 and 160),
    address text not null default '',
    timezone text not null,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, id),
    unique (organization_id, name)
);

create table if not exists public.departments (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    name text not null check (char_length(trim(name)) between 1 and 160),
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, id),
    unique (organization_id, name)
);

create table if not exists public.doctors (
    id uuid primary key default gen_random_uuid(),
    canonical_name text not null check (char_length(trim(canonical_name)) between 1 and 160),
    qualifications text[] not null default '{}',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.organization_users (
    organization_id uuid not null references public.organizations(id) on delete restrict,
    auth_user_id uuid not null references auth.users(id) on delete restrict,
    role text not null check (role in ('ORG_ADMIN', 'RECEPTIONIST', 'VIEWER')),
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (organization_id, auth_user_id)
);

create table if not exists public.doctor_assignments (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    doctor_id uuid not null references public.doctors(id) on delete restrict,
    location_id uuid not null,
    department_id uuid not null,
    display_name text not null check (char_length(trim(display_name)) between 1 and 160),
    fee_minor integer not null default 0 check (fee_minor >= 0),
    currency char(3) not null default 'INR',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, id),
    unique (organization_id, doctor_id, location_id, department_id),
    constraint doctor_assignments_location_tenant_fk
        foreign key (organization_id, location_id)
        references public.locations (organization_id, id) on delete restrict,
    constraint doctor_assignments_department_tenant_fk
        foreign key (organization_id, department_id)
        references public.departments (organization_id, id) on delete restrict
);

create table if not exists public.audit_events (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    actor_type text not null check (actor_type in ('USER', 'SYSTEM', 'PROVIDER')),
    actor_id uuid,
    action text not null check (char_length(trim(action)) between 1 and 160),
    entity_type text not null check (char_length(trim(entity_type)) between 1 and 80),
    entity_id uuid,
    safe_change_summary jsonb not null default '{}'::jsonb,
    correlation_id uuid,
    occurred_at timestamptz not null default now()
);

create index if not exists organization_users_auth_user_id_active_idx
    on public.organization_users (auth_user_id, organization_id) where active;
create index if not exists locations_organization_id_active_idx
    on public.locations (organization_id, active);
create index if not exists departments_organization_id_active_idx
    on public.departments (organization_id, active);
create index if not exists doctor_assignments_organization_id_active_idx
    on public.doctor_assignments (organization_id, active);
create index if not exists audit_events_organization_id_occurred_at_idx
    on public.audit_events (organization_id, occurred_at desc);

create or replace function private.set_updated_at()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create or replace function private.prevent_audit_mutation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    raise exception 'audit_events are append-only';
end;
$$;

create or replace function private.is_org_member(target_organization_id uuid)
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
    );
$$;

create or replace function private.is_org_admin(target_organization_id uuid)
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
          and membership.role = 'ORG_ADMIN'
    );
$$;

create or replace function public.create_organization_with_admin(
    p_name text,
    p_organization_type text,
    p_timezone text default 'Asia/Kolkata'
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    created_organization_id uuid;
begin
    if (select auth.uid()) is null then
        raise exception 'authenticated user required';
    end if;
    if p_organization_type not in ('CLINIC', 'HOSPITAL') then
        raise exception 'invalid organization type';
    end if;
    if nullif(trim(p_name), '') is null then
        raise exception 'organization name required';
    end if;
    insert into public.organizations (name, organization_type, timezone)
    values (trim(p_name), p_organization_type, p_timezone)
    returning id into created_organization_id;
    insert into public.organization_users (organization_id, auth_user_id, role)
    values (created_organization_id, (select auth.uid()), 'ORG_ADMIN');
    return created_organization_id;
end;
$$;

revoke all on function private.set_updated_at() from public;
revoke all on function private.prevent_audit_mutation() from public;
revoke all on function private.is_org_member(uuid) from public;
revoke all on function private.is_org_admin(uuid) from public;
grant execute on function private.is_org_member(uuid) to authenticated;
grant execute on function private.is_org_admin(uuid) to authenticated;
revoke all on function public.create_organization_with_admin(text, text, text) from public;
grant execute on function public.create_organization_with_admin(text, text, text) to authenticated;

drop trigger if exists organizations_set_updated_at on public.organizations;
create trigger organizations_set_updated_at before update on public.organizations
for each row execute function private.set_updated_at();
drop trigger if exists locations_set_updated_at on public.locations;
create trigger locations_set_updated_at before update on public.locations
for each row execute function private.set_updated_at();
drop trigger if exists departments_set_updated_at on public.departments;
create trigger departments_set_updated_at before update on public.departments
for each row execute function private.set_updated_at();
drop trigger if exists doctors_set_updated_at on public.doctors;
create trigger doctors_set_updated_at before update on public.doctors
for each row execute function private.set_updated_at();
drop trigger if exists organization_users_set_updated_at on public.organization_users;
create trigger organization_users_set_updated_at before update on public.organization_users
for each row execute function private.set_updated_at();
drop trigger if exists doctor_assignments_set_updated_at on public.doctor_assignments;
create trigger doctor_assignments_set_updated_at before update on public.doctor_assignments
for each row execute function private.set_updated_at();
drop trigger if exists audit_events_immutable on public.audit_events;
create trigger audit_events_immutable before update or delete on public.audit_events
for each row execute function private.prevent_audit_mutation();

alter table public.organizations enable row level security;
alter table public.locations enable row level security;
alter table public.departments enable row level security;
alter table public.doctors enable row level security;
alter table public.organization_users enable row level security;
alter table public.doctor_assignments enable row level security;
alter table public.audit_events enable row level security;

drop policy if exists organizations_member_select on public.organizations;
create policy organizations_member_select on public.organizations for select to authenticated
using ((select private.is_org_member(id)));
drop policy if exists organizations_admin_update on public.organizations;
create policy organizations_admin_update on public.organizations for update to authenticated
using ((select private.is_org_admin(id)))
with check ((select private.is_org_admin(id)));

drop policy if exists locations_member_select on public.locations;
create policy locations_member_select on public.locations for select to authenticated
using ((select private.is_org_member(organization_id)));
drop policy if exists locations_admin_write on public.locations;
create policy locations_admin_write on public.locations for all to authenticated
using ((select private.is_org_admin(organization_id)))
with check ((select private.is_org_admin(organization_id)));

drop policy if exists departments_member_select on public.departments;
create policy departments_member_select on public.departments for select to authenticated
using ((select private.is_org_member(organization_id)));
drop policy if exists departments_admin_write on public.departments;
create policy departments_admin_write on public.departments for all to authenticated
using ((select private.is_org_admin(organization_id)))
with check ((select private.is_org_admin(organization_id)));

drop policy if exists organization_users_own_or_admin_select on public.organization_users;
create policy organization_users_own_or_admin_select on public.organization_users for select to authenticated
using (auth_user_id = (select auth.uid()) or (select private.is_org_admin(organization_id)));
drop policy if exists organization_users_admin_write on public.organization_users;
create policy organization_users_admin_write on public.organization_users for all to authenticated
using ((select private.is_org_admin(organization_id)))
with check ((select private.is_org_admin(organization_id)));

drop policy if exists doctors_assigned_member_select on public.doctors;
create policy doctors_assigned_member_select on public.doctors for select to authenticated
using (
    exists (
        select 1 from public.doctor_assignments as assignment
        where assignment.doctor_id = doctors.id
          and (select private.is_org_member(assignment.organization_id))
    )
);

drop policy if exists doctor_assignments_member_select on public.doctor_assignments;
create policy doctor_assignments_member_select on public.doctor_assignments for select to authenticated
using ((select private.is_org_member(organization_id)));
drop policy if exists doctor_assignments_admin_write on public.doctor_assignments;
create policy doctor_assignments_admin_write on public.doctor_assignments for all to authenticated
using ((select private.is_org_admin(organization_id)))
with check ((select private.is_org_admin(organization_id)));

drop policy if exists audit_events_admin_select on public.audit_events;
create policy audit_events_admin_select on public.audit_events for select to authenticated
using ((select private.is_org_admin(organization_id)));

commit;

