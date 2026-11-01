-- Phase: 2.1 — Scheduling foundation
-- Requirements: SCH-01, SCH-02, DOC-01, TEN-01, TEN-02
-- Apply after 20260910000100_phase1_tenant_foundation.sql.
-- Recovery: additive schema only. Do not delete generated sessions or slots if reservations exist.

begin;

create extension if not exists btree_gist;

create table public.schedule_rules (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    assignment_id uuid not null,
    weekday smallint not null check (weekday between 0 and 6),
    local_starts_at time not null,
    local_ends_at time not null,
    booking_mode text not null check (booking_mode in ('EXACT_TIME', 'SESSION_TOKEN')),
    slot_minutes smallint,
    max_patients integer,
    effective_from date not null,
    effective_until date,
    booking_cutoff_minutes integer not null default 30 check (booking_cutoff_minutes >= 0 and booking_cutoff_minutes <= 10080),
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint schedule_rules_assignment_tenant_fk
        foreign key (organization_id, assignment_id)
        references public.doctor_assignments (organization_id, id) on delete restrict,
    constraint schedule_rules_local_window_check
        check (local_ends_at > local_starts_at),
    constraint schedule_rules_effective_dates_check
        check (effective_until is null or effective_until >= effective_from),
    constraint schedule_rules_mode_configuration_check
        check (
            (booking_mode = 'EXACT_TIME' and slot_minutes between 5 and 240 and max_patients is null)
            or
            (booking_mode = 'SESSION_TOKEN' and max_patients between 1 and 1000 and slot_minutes is null)
        ),
    unique (organization_id, id)
);

create table public.schedule_exceptions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    assignment_id uuid not null,
    local_date date not null,
    exception_type text not null check (exception_type in ('CLOSED', 'REPLACEMENT_HOURS')),
    local_starts_at time,
    local_ends_at time,
    reason text not null default '' check (char_length(reason) <= 500),
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint schedule_exceptions_assignment_tenant_fk
        foreign key (organization_id, assignment_id)
        references public.doctor_assignments (organization_id, id) on delete restrict,
    constraint schedule_exceptions_window_check
        check (
            (exception_type = 'CLOSED' and local_starts_at is null and local_ends_at is null)
            or
            (exception_type = 'REPLACEMENT_HOURS' and local_starts_at is not null and local_ends_at is not null and local_ends_at > local_starts_at)
        ),
    unique (organization_id, assignment_id, local_date),
    unique (organization_id, id)
);

create table public.appointment_sessions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    assignment_id uuid not null,
    doctor_id uuid not null references public.doctors(id) on delete restrict,
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    timezone text not null,
    booking_mode text not null check (booking_mode in ('EXACT_TIME', 'SESSION_TOKEN')),
    slot_minutes smallint,
    max_patients integer,
    next_token integer not null default 0 check (next_token >= 0),
    booking_cutoff_minutes integer not null default 30 check (booking_cutoff_minutes >= 0 and booking_cutoff_minutes <= 10080),
    status text not null default 'SCHEDULED' check (status in ('SCHEDULED', 'OPEN', 'CLOSED', 'CANCELLED')),
    generation_version integer not null default 1 check (generation_version > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint appointment_sessions_assignment_tenant_fk
        foreign key (organization_id, assignment_id)
        references public.doctor_assignments (organization_id, id) on delete restrict,
    constraint appointment_sessions_window_check check (ends_at > starts_at),
    constraint appointment_sessions_mode_configuration_check
        check (
            (booking_mode = 'EXACT_TIME' and slot_minutes between 5 and 240 and max_patients is null and next_token = 0)
            or
            (booking_mode = 'SESSION_TOKEN' and max_patients between 1 and 1000 and slot_minutes is null)
        ),
    unique (organization_id, id),
    unique (organization_id, assignment_id, starts_at)
);

create table public.appointment_slots (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    session_id uuid not null,
    assignment_id uuid not null,
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    bookable boolean not null default true,
    generation_version integer not null default 1 check (generation_version > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint appointment_slots_session_tenant_fk
        foreign key (organization_id, session_id)
        references public.appointment_sessions (organization_id, id) on delete restrict,
    constraint appointment_slots_assignment_tenant_fk
        foreign key (organization_id, assignment_id)
        references public.doctor_assignments (organization_id, id) on delete restrict,
    constraint appointment_slots_window_check check (ends_at > starts_at),
    unique (organization_id, id),
    unique (organization_id, session_id, starts_at)
);

create index schedule_rules_organization_assignment_active_idx
    on public.schedule_rules (organization_id, assignment_id, weekday) where active;
create index schedule_exceptions_organization_assignment_date_active_idx
    on public.schedule_exceptions (organization_id, assignment_id, local_date) where active;
create index appointment_sessions_organization_assignment_starts_at_idx
    on public.appointment_sessions (organization_id, assignment_id, starts_at);
create index appointment_sessions_organization_doctor_starts_at_idx
    on public.appointment_sessions (organization_id, doctor_id, starts_at);
create index appointment_slots_organization_session_starts_at_idx
    on public.appointment_slots (organization_id, session_id, starts_at) where bookable;

create or replace function private.enforce_session_assignment_doctor()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    assignment_doctor_id uuid;
begin
    select doctor_id into assignment_doctor_id
    from public.doctor_assignments
    where organization_id = new.organization_id and id = new.assignment_id and active = true;

    if assignment_doctor_id is null then
        raise exception 'active tenant-scoped doctor assignment required';
    end if;
    if assignment_doctor_id <> new.doctor_id then
        raise exception 'session doctor must match assignment doctor';
    end if;
    return new;
end;
$$;

create or replace function private.enforce_slot_session_shape()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    session_row public.appointment_sessions%rowtype;
begin
    select * into session_row
    from public.appointment_sessions
    where organization_id = new.organization_id and id = new.session_id;

    if not found then
        raise exception 'tenant-scoped appointment session required';
    end if;
    if session_row.booking_mode <> 'EXACT_TIME' then
        raise exception 'slots are only allowed for exact-time sessions';
    end if;
    if new.assignment_id <> session_row.assignment_id
       or new.starts_at < session_row.starts_at
       or new.ends_at > session_row.ends_at
       or new.ends_at - new.starts_at <> make_interval(mins => session_row.slot_minutes) then
        raise exception 'slot must match its exact-time session';
    end if;
    return new;
end;
$$;

revoke all on function private.enforce_session_assignment_doctor() from public;
revoke all on function private.enforce_slot_session_shape() from public;

alter table public.appointment_sessions
    add constraint appointment_sessions_doctor_time_exclusion
    exclude using gist (
        doctor_id with =,
        tstzrange(starts_at, ends_at, '[)') with &&
    ) where (status <> 'CANCELLED');

drop trigger if exists schedule_rules_set_updated_at on public.schedule_rules;
create trigger schedule_rules_set_updated_at before update on public.schedule_rules
for each row execute function private.set_updated_at();
drop trigger if exists schedule_exceptions_set_updated_at on public.schedule_exceptions;
create trigger schedule_exceptions_set_updated_at before update on public.schedule_exceptions
for each row execute function private.set_updated_at();
drop trigger if exists appointment_sessions_set_updated_at on public.appointment_sessions;
create trigger appointment_sessions_set_updated_at before update on public.appointment_sessions
for each row execute function private.set_updated_at();
drop trigger if exists appointment_slots_set_updated_at on public.appointment_slots;
create trigger appointment_slots_set_updated_at before update on public.appointment_slots
for each row execute function private.set_updated_at();
drop trigger if exists appointment_sessions_enforce_assignment_doctor on public.appointment_sessions;
create trigger appointment_sessions_enforce_assignment_doctor
before insert or update of organization_id, assignment_id, doctor_id on public.appointment_sessions
for each row execute function private.enforce_session_assignment_doctor();
drop trigger if exists appointment_slots_enforce_session_shape on public.appointment_slots;
create trigger appointment_slots_enforce_session_shape
before insert or update of organization_id, session_id, assignment_id, starts_at, ends_at on public.appointment_slots
for each row execute function private.enforce_slot_session_shape();

alter table public.schedule_rules enable row level security;
alter table public.schedule_exceptions enable row level security;
alter table public.appointment_sessions enable row level security;
alter table public.appointment_slots enable row level security;

create policy schedule_rules_member_select on public.schedule_rules for select to authenticated
using ((select private.is_org_member(organization_id)));
create policy schedule_rules_admin_write on public.schedule_rules for all to authenticated
using ((select private.is_org_admin(organization_id)))
with check ((select private.is_org_admin(organization_id)));
create policy schedule_exceptions_member_select on public.schedule_exceptions for select to authenticated
using ((select private.is_org_member(organization_id)));
create policy schedule_exceptions_admin_write on public.schedule_exceptions for all to authenticated
using ((select private.is_org_admin(organization_id)))
with check ((select private.is_org_admin(organization_id)));
create policy appointment_sessions_member_select on public.appointment_sessions for select to authenticated
using ((select private.is_org_member(organization_id)));
create policy appointment_sessions_admin_write on public.appointment_sessions for all to authenticated
using ((select private.is_org_admin(organization_id)))
with check ((select private.is_org_admin(organization_id)));
create policy appointment_slots_member_select on public.appointment_slots for select to authenticated
using ((select private.is_org_member(organization_id)));
create policy appointment_slots_admin_write on public.appointment_slots for all to authenticated
using ((select private.is_org_admin(organization_id)))
with check ((select private.is_org_admin(organization_id)));

commit;
