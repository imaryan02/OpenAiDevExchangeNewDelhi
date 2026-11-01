-- Phase: 2.2c — Transactional holds, confirmation, expiry and token allocation
-- Requirements: SCH-02, QUE-01, CHG-01, PAY-01
-- Apply after 20260911000300_phase2_appointments.sql.
-- Recovery: functions are replaceable. Appointment history remains append-only in meaning.

begin;

create table public.idempotency_records (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    actor_scope text not null,
    operation text not null,
    idempotency_key text not null check (char_length(idempotency_key) between 16 and 255),
    request_hash text not null check (char_length(request_hash) >= 32),
    response_appointment_id uuid references public.appointments(id) on delete restrict,
    created_at timestamptz not null default now(),
    unique (organization_id, actor_scope, operation, idempotency_key)
);

create index idempotency_records_organization_created_at_idx
    on public.idempotency_records (organization_id, created_at);

create or replace function private.enforce_appointment_contact_route()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
    phone_contact_id uuid;
begin
    if new.booked_by_contact_id is null then
        raise exception 'appointment booker contact is required';
    end if;
    if new.notification_contact_phone_id is not null then
        select contact_id into phone_contact_id
        from public.contact_phones
        where organization_id = new.organization_id
          and id = new.notification_contact_phone_id
          and status = 'ACTIVE';
        if phone_contact_id is distinct from new.booked_by_contact_id then
            raise exception 'notification phone must be an active phone owned by the booking contact';
        end if;
    end if;
    return new;
end;
$$;

create or replace function public.create_simulated_appointment_hold(
    p_organization_id uuid,
    p_patient_id uuid,
    p_booked_by_contact_id uuid,
    p_notification_contact_phone_id uuid,
    p_assignment_id uuid,
    p_session_id uuid,
    p_slot_id uuid,
    p_source text,
    p_idempotency_key text,
    p_request_hash text,
    p_hold_seconds integer default 600
)
returns table (appointment_id uuid, booking_reference text, status text, hold_expires_at timestamptz)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
    session_row public.appointment_sessions%rowtype;
    existing_record public.idempotency_records%rowtype;
    appointment_row public.appointments%rowtype;
    occupancy integer;
    now_at timestamptz := now();
begin
    if not (select private.is_org_booking_staff(p_organization_id)) then
        raise exception 'booking staff authorization required';
    end if;
    if p_hold_seconds not between 60 and 1800 then
        raise exception 'hold duration must be between 60 and 1800 seconds';
    end if;

    select * into existing_record from public.idempotency_records
    where organization_id = p_organization_id
      and actor_scope = (select auth.uid())::text
      and operation = 'CREATE_SIMULATED_HOLD'
      and idempotency_key = p_idempotency_key
    for update;
    if found then
        if existing_record.request_hash <> p_request_hash then
            raise exception 'idempotency key was reused with a different request';
        end if;
        select * into appointment_row from public.appointments
        where organization_id = p_organization_id and id = existing_record.response_appointment_id;
        return query select appointment_row.id, appointment_row.booking_reference, appointment_row.status, appointment_row.hold_expires_at;
        return;
    end if;

    select * into session_row from public.appointment_sessions
    where organization_id = p_organization_id and id = p_session_id
    for update;
    if not found or session_row.assignment_id <> p_assignment_id or session_row.status not in ('SCHEDULED', 'OPEN') then
        raise exception 'bookable tenant-scoped session required';
    end if;
    if now_at >= session_row.starts_at - make_interval(mins => session_row.booking_cutoff_minutes) then
        raise exception 'booking cutoff has passed';
    end if;

    update public.appointments
    set status = 'EXPIRED', hold_expires_at = null
    where organization_id = p_organization_id
      and session_id = p_session_id
      and status = 'PAYMENT_PENDING'
      and hold_expires_at <= now_at;

    if session_row.booking_mode = 'EXACT_TIME' then
        if p_slot_id is null then raise exception 'exact-time session requires a slot'; end if;
        perform 1 from public.appointment_slots
        where organization_id = p_organization_id and id = p_slot_id and session_id = p_session_id and bookable = true
        for update;
        if not found then raise exception 'bookable matching slot required'; end if;
    else
        if p_slot_id is not null then raise exception 'token session cannot receive a slot'; end if;
        select count(*) into occupancy from public.appointments
        where organization_id = p_organization_id and session_id = p_session_id
          and status in ('PAYMENT_PENDING', 'CONFIRMED', 'COMPLETED', 'NO_SHOW');
        if occupancy >= session_row.max_patients then raise exception 'session capacity is full'; end if;
    end if;

    insert into public.appointments (
        organization_id, patient_id, booked_by_contact_id, notification_contact_phone_id,
        assignment_id, session_id, slot_id, status, hold_expires_at, source,
        fee_minor, currency, contact_snapshot, quote_snapshot, consent_snapshot
    )
    select p_organization_id, p_patient_id, p_booked_by_contact_id, p_notification_contact_phone_id,
           p_assignment_id, p_session_id, p_slot_id, 'PAYMENT_PENDING', now_at + make_interval(secs => p_hold_seconds), p_source,
           assignment.fee_minor, assignment.currency, '{}'::jsonb,
           jsonb_build_object('booking_mode', session_row.booking_mode, 'fee_minor', assignment.fee_minor, 'currency', assignment.currency),
           '{}'::jsonb
    from public.doctor_assignments assignment
    where assignment.organization_id = p_organization_id and assignment.id = p_assignment_id and assignment.active
    returning * into appointment_row;
    if not found then raise exception 'active tenant-scoped doctor assignment required'; end if;

    insert into public.appointment_contact_permissions (organization_id, appointment_id, contact_id, can_view, can_manage, grant_source)
    values (p_organization_id, appointment_row.id, p_booked_by_contact_id, true, true, 'BOOKING');
    insert into public.payment_attempts (organization_id, appointment_id, reference, amount_minor, currency, status)
    values (p_organization_id, appointment_row.id, appointment_row.booking_reference, appointment_row.fee_minor, appointment_row.currency, 'SIMULATION_PENDING');
    insert into public.idempotency_records (organization_id, actor_scope, operation, idempotency_key, request_hash, response_appointment_id)
    values (p_organization_id, (select auth.uid())::text, 'CREATE_SIMULATED_HOLD', p_idempotency_key, p_request_hash, appointment_row.id);
    return query select appointment_row.id, appointment_row.booking_reference, appointment_row.status, appointment_row.hold_expires_at;
end;
$$;

create or replace function public.confirm_simulated_appointment(
    p_organization_id uuid,
    p_appointment_id uuid
)
returns table (appointment_id uuid, booking_reference text, status text, token_number integer)
language plpgsql
security definer
set search_path = ''
as $$
declare
    appointment_row public.appointments%rowtype;
    session_row public.appointment_sessions%rowtype;
    allocated_token integer;
begin
    if not (select private.is_org_booking_staff(p_organization_id)) then raise exception 'booking staff authorization required'; end if;
    select * into appointment_row from public.appointments
    where organization_id = p_organization_id and id = p_appointment_id for update;
    if not found then raise exception 'appointment not found'; end if;
    if appointment_row.status = 'CONFIRMED' then
        return query select appointment_row.id, appointment_row.booking_reference, appointment_row.status, appointment_row.token_number;
        return;
    end if;
    if appointment_row.status <> 'PAYMENT_PENDING' or appointment_row.hold_expires_at <= now() then
        raise exception 'appointment hold is not eligible for confirmation';
    end if;
    select * into session_row from public.appointment_sessions
    where organization_id = p_organization_id and id = appointment_row.session_id for update;
    if session_row.booking_mode = 'SESSION_TOKEN' then
        update public.appointment_sessions set next_token = next_token + 1
        where organization_id = p_organization_id and id = session_row.id
        returning next_token into allocated_token;
    end if;
    update public.appointments
    set status = 'CONFIRMED', hold_expires_at = null, token_number = allocated_token, queue_status = 'NOT_ARRIVED', version = version + 1
    where organization_id = p_organization_id and id = p_appointment_id
    returning * into appointment_row;
    update public.payment_attempts set status = 'SIMULATED_SUCCESS'
    where organization_id = p_organization_id and appointment_id = p_appointment_id and status = 'SIMULATION_PENDING';
    return query select appointment_row.id, appointment_row.booking_reference, appointment_row.status, appointment_row.token_number;
end;
$$;

create or replace function public.expire_simulated_appointment_holds()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare expired_count integer;
begin
    update public.appointments set status = 'EXPIRED', hold_expires_at = null, version = version + 1
    where status = 'PAYMENT_PENDING' and hold_expires_at <= now();
    get diagnostics expired_count = row_count;
    update public.payment_attempts set status = 'SIMULATED_FAILURE'
    where status = 'SIMULATION_PENDING'
      and appointment_id in (select id from public.appointments where status = 'EXPIRED');
    return expired_count;
end;
$$;

revoke all on function public.create_simulated_appointment_hold(uuid, uuid, uuid, uuid, uuid, uuid, uuid, text, text, text, integer) from public;
revoke all on function public.confirm_simulated_appointment(uuid, uuid) from public;
revoke all on function public.expire_simulated_appointment_holds() from public;
grant execute on function public.create_simulated_appointment_hold(uuid, uuid, uuid, uuid, uuid, uuid, uuid, text, text, text, integer) to authenticated;
grant execute on function public.confirm_simulated_appointment(uuid, uuid) to authenticated;

drop trigger if exists appointments_enforce_contact_route on public.appointments;
create trigger appointments_enforce_contact_route before insert or update of organization_id, booked_by_contact_id, notification_contact_phone_id on public.appointments
for each row execute function private.enforce_appointment_contact_route();

alter table public.idempotency_records enable row level security;

commit;
