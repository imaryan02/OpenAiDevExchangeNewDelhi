-- Phase: 2.2b — Appointment, authorization, verification and simulated payment records
-- Requirements: QUE-01, PAT-02, RET-01, RET-02, CHG-01
-- Apply after 20260911000200_phase2_contact_patient_identity.sql.
-- Recovery: additive schema only. Appointment rows are historical records; never delete them.

begin;

create table public.appointments (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    patient_id uuid not null,
    booked_by_contact_id uuid,
    notification_contact_phone_id uuid,
    assignment_id uuid not null,
    session_id uuid not null,
    slot_id uuid,
    booking_reference text not null default ('GM-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10))),
    token_number integer,
    queue_status text,
    status text not null check (status in ('PAYMENT_PENDING', 'CONFIRMED', 'CANCELLED', 'RESCHEDULED', 'COMPLETED', 'NO_SHOW', 'EXPIRED')),
    hold_expires_at timestamptz,
    source text not null check (source in ('AI_VOICE', 'AI_TEXT', 'STAFF', 'WALK_IN')),
    version integer not null default 1 check (version > 0),
    fee_minor integer not null default 0 check (fee_minor >= 0),
    currency char(3) not null default 'INR',
    contact_snapshot jsonb not null default '{}'::jsonb,
    quote_snapshot jsonb not null default '{}'::jsonb,
    consent_snapshot jsonb not null default '{}'::jsonb,
    supersedes_appointment_id uuid references public.appointments(id) on delete restrict,
    cancelled_at timestamptz,
    cancellation_reason text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint appointments_patient_tenant_fk foreign key (organization_id, patient_id) references public.patients (organization_id, id) on delete restrict,
    constraint appointments_booker_tenant_fk foreign key (organization_id, booked_by_contact_id) references public.contacts (organization_id, id) on delete restrict,
    constraint appointments_notification_phone_tenant_fk foreign key (organization_id, notification_contact_phone_id) references public.contact_phones (organization_id, id) on delete restrict,
    constraint appointments_assignment_tenant_fk foreign key (organization_id, assignment_id) references public.doctor_assignments (organization_id, id) on delete restrict,
    constraint appointments_session_tenant_fk foreign key (organization_id, session_id) references public.appointment_sessions (organization_id, id) on delete restrict,
    constraint appointments_slot_tenant_fk foreign key (organization_id, slot_id) references public.appointment_slots (organization_id, id) on delete restrict,
    constraint appointments_reference_format_check check (booking_reference ~ '^GM-[A-Z0-9]{10}$'),
    constraint appointments_token_check check (token_number is null or token_number > 0),
    constraint appointments_queue_state_check check (queue_status is null or queue_status in ('NOT_ARRIVED', 'CHECKED_IN', 'CALLED', 'IN_CONSULTATION', 'SERVED', 'SKIPPED')),
    constraint appointments_hold_check check ((status = 'PAYMENT_PENDING' and hold_expires_at is not null) or (status <> 'PAYMENT_PENDING' and hold_expires_at is null)),
    constraint appointments_cancellation_check check ((status = 'CANCELLED' and cancelled_at is not null and cancellation_reason is not null) or status <> 'CANCELLED'),
    unique (organization_id, id),
    unique (organization_id, booking_reference)
);

create unique index appointments_active_exact_slot_idx
    on public.appointments (organization_id, slot_id)
    where slot_id is not null and status in ('PAYMENT_PENDING', 'CONFIRMED', 'COMPLETED', 'NO_SHOW');
create unique index appointments_session_token_idx
    on public.appointments (organization_id, session_id, token_number)
    where token_number is not null;
create index appointments_organization_patient_created_at_idx on public.appointments (organization_id, patient_id, created_at desc);
create index appointments_organization_booker_created_at_idx on public.appointments (organization_id, booked_by_contact_id, created_at desc);
create index appointments_organization_session_status_idx on public.appointments (organization_id, session_id, status);

create table public.appointment_contact_permissions (
    organization_id uuid not null references public.organizations(id) on delete restrict,
    appointment_id uuid not null,
    contact_id uuid not null,
    can_view boolean not null default true,
    can_manage boolean not null default false,
    grant_source text not null check (grant_source in ('BOOKING', 'STAFF', 'AUTHORIZED_WORKFLOW')),
    granted_at timestamptz not null default now(),
    revoked_at timestamptz,
    constraint appointment_contact_permissions_appointment_tenant_fk foreign key (organization_id, appointment_id) references public.appointments (organization_id, id) on delete restrict,
    constraint appointment_contact_permissions_contact_tenant_fk foreign key (organization_id, contact_id) references public.contacts (organization_id, id) on delete restrict,
    constraint appointment_contact_permissions_manage_implies_view check (can_manage = false or can_view = true),
    primary key (organization_id, appointment_id, contact_id)
);

create index appointment_contact_permissions_contact_active_idx
    on public.appointment_contact_permissions (organization_id, contact_id, appointment_id) where revoked_at is null;

create table public.verification_challenges (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    call_id uuid,
    contact_phone_id uuid not null,
    phone_version integer not null check (phone_version > 0),
    code_digest text not null check (char_length(code_digest) >= 32),
    expires_at timestamptz not null,
    attempt_count integer not null default 0 check (attempt_count between 0 and 5),
    consumed_at timestamptz,
    verified_until timestamptz,
    status text not null default 'PENDING' check (status in ('PENDING', 'VERIFIED', 'EXPIRED', 'LOCKED', 'CANCELLED')),
    created_at timestamptz not null default now(),
    constraint verification_challenges_phone_tenant_fk foreign key (organization_id, contact_phone_id) references public.contact_phones (organization_id, id) on delete restrict,
    constraint verification_challenges_expiry_check check (expires_at > created_at),
    constraint verification_challenges_verified_check check ((status = 'VERIFIED' and consumed_at is not null and verified_until is not null) or status <> 'VERIFIED'),
    unique (organization_id, id)
);

create index verification_challenges_active_phone_idx
    on public.verification_challenges (organization_id, contact_phone_id, expires_at)
    where status = 'PENDING';

create table public.payment_attempts (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    appointment_id uuid not null,
    provider text not null default 'LOCAL_SIMULATOR',
    mode text not null default 'SIMULATED' check (mode in ('SIMULATED', 'PAY_AT_CLINIC', 'WAIVED')),
    reference text not null,
    amount_minor integer not null check (amount_minor >= 0),
    currency char(3) not null default 'INR',
    status text not null check (status in ('SIMULATION_PENDING', 'SIMULATED_SUCCESS', 'SIMULATED_FAILURE', 'DUE_AT_CLINIC', 'WAIVED')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint payment_attempts_appointment_tenant_fk foreign key (organization_id, appointment_id) references public.appointments (organization_id, id) on delete restrict,
    unique (organization_id, reference),
    unique (organization_id, id)
);

create index payment_attempts_organization_appointment_idx on public.payment_attempts (organization_id, appointment_id, created_at desc);

create or replace function private.enforce_appointment_session_shape()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    session_row public.appointment_sessions%rowtype;
    slot_row public.appointment_slots%rowtype;
begin
    select * into session_row from public.appointment_sessions
    where organization_id = new.organization_id and id = new.session_id;
    if not found or session_row.assignment_id <> new.assignment_id then
        raise exception 'appointment assignment must match tenant-scoped session';
    end if;
    if session_row.booking_mode = 'EXACT_TIME' then
        if new.slot_id is null or new.token_number is not null then
            raise exception 'exact-time appointment requires a slot and cannot have a token';
        end if;
        select * into slot_row from public.appointment_slots
        where organization_id = new.organization_id and id = new.slot_id;
        if not found or slot_row.session_id <> new.session_id or slot_row.assignment_id <> new.assignment_id then
            raise exception 'appointment slot must match session and assignment';
        end if;
    elsif new.slot_id is not null then
        raise exception 'token-session appointment cannot have an exact-time slot';
    end if;
    if new.token_number is not null and session_row.booking_mode <> 'SESSION_TOKEN' then
        raise exception 'tokens belong only to token sessions';
    end if;
    return new;
end;
$$;

revoke all on function private.enforce_appointment_session_shape() from public;

drop trigger if exists appointments_set_updated_at on public.appointments;
create trigger appointments_set_updated_at before update on public.appointments for each row execute function private.set_updated_at();
drop trigger if exists payment_attempts_set_updated_at on public.payment_attempts;
create trigger payment_attempts_set_updated_at before update on public.payment_attempts for each row execute function private.set_updated_at();
drop trigger if exists appointments_enforce_session_shape on public.appointments;
create trigger appointments_enforce_session_shape before insert or update of organization_id, assignment_id, session_id, slot_id, token_number on public.appointments for each row execute function private.enforce_appointment_session_shape();

alter table public.appointments enable row level security;
alter table public.appointment_contact_permissions enable row level security;
alter table public.verification_challenges enable row level security;
alter table public.payment_attempts enable row level security;

create policy appointments_booking_staff_select on public.appointments for select to authenticated using ((select private.is_org_booking_staff(organization_id)));
create policy appointments_booking_staff_write on public.appointments for all to authenticated using ((select private.is_org_booking_staff(organization_id))) with check ((select private.is_org_booking_staff(organization_id)));
create policy appointment_permissions_booking_staff_select on public.appointment_contact_permissions for select to authenticated using ((select private.is_org_booking_staff(organization_id)));
create policy appointment_permissions_booking_staff_write on public.appointment_contact_permissions for all to authenticated using ((select private.is_org_booking_staff(organization_id))) with check ((select private.is_org_booking_staff(organization_id)));
create policy payment_attempts_booking_staff_select on public.payment_attempts for select to authenticated using ((select private.is_org_booking_staff(organization_id)));
create policy payment_attempts_booking_staff_write on public.payment_attempts for all to authenticated using ((select private.is_org_booking_staff(organization_id))) with check ((select private.is_org_booking_staff(organization_id)));

commit;
