-- Phase: 2.3a — Cancellation and durable notification outbox
-- Apply after 20260911000400_phase2_transactional_booking.sql.

begin;

create table public.outbox_jobs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    job_type text not null check (job_type in ('APPOINTMENT_CONFIRMED', 'APPOINTMENT_CANCELLED', 'APPOINTMENT_RESCHEDULED')),
    aggregate_id uuid not null,
    dedupe_key text not null,
    payload jsonb not null default '{}'::jsonb,
    attempts integer not null default 0 check (attempts >= 0),
    next_attempt_at timestamptz not null default now(),
    lease_until timestamptz,
    status text not null default 'PENDING' check (status in ('PENDING', 'PROCESSING', 'SENT', 'FAILED', 'DEAD_LETTER')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, dedupe_key)
);

create index outbox_jobs_dispatch_idx on public.outbox_jobs (status, next_attempt_at) where status in ('PENDING', 'FAILED');

create or replace function public.cancel_appointment(
    p_organization_id uuid,
    p_appointment_id uuid,
    p_expected_version integer,
    p_reason text
)
returns table (appointment_id uuid, booking_reference text, status text, version integer)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare appointment_row public.appointments%rowtype;
begin
    if not (select private.is_org_booking_staff(p_organization_id)) then
        raise exception 'booking staff authorization required';
    end if;
    if nullif(trim(p_reason), '') is null then
        raise exception 'cancellation reason is required';
    end if;
    select * into appointment_row from public.appointments
    where organization_id = p_organization_id and id = p_appointment_id
    for update;
    if not found then raise exception 'appointment not found'; end if;
    if appointment_row.version <> p_expected_version then raise exception 'appointment changed; reload before cancelling'; end if;
    if appointment_row.status not in ('PAYMENT_PENDING', 'CONFIRMED') then raise exception 'appointment cannot be cancelled in its current state'; end if;

    update public.appointments
    set status = 'CANCELLED', hold_expires_at = null, queue_status = null,
        cancelled_at = now(), cancellation_reason = trim(p_reason), version = version + 1
    where organization_id = p_organization_id and id = p_appointment_id
    returning * into appointment_row;
    update public.payment_attempts set status = 'SIMULATED_FAILURE'
    where organization_id = p_organization_id and appointment_id = p_appointment_id and status = 'SIMULATION_PENDING';
    insert into public.outbox_jobs (organization_id, job_type, aggregate_id, dedupe_key, payload)
    values (p_organization_id, 'APPOINTMENT_CANCELLED', appointment_row.id,
            'appointment-cancelled:' || appointment_row.id::text,
            jsonb_build_object('appointment_id', appointment_row.id, 'booking_reference', appointment_row.booking_reference));
    insert into public.audit_events (organization_id, actor_type, actor_id, action, entity_type, entity_id, safe_change_summary)
    values (p_organization_id, 'USER', (select auth.uid()), 'APPOINTMENT_CANCELLED', 'APPOINTMENT', appointment_row.id,
            jsonb_build_object('reason', trim(p_reason)));
    return query select appointment_row.id, appointment_row.booking_reference, appointment_row.status, appointment_row.version;
end;
$$;

revoke all on function public.cancel_appointment(uuid, uuid, integer, text) from public;
grant execute on function public.cancel_appointment(uuid, uuid, integer, text) to authenticated;
drop trigger if exists outbox_jobs_set_updated_at on public.outbox_jobs;
create trigger outbox_jobs_set_updated_at before update on public.outbox_jobs for each row execute function private.set_updated_at();
alter table public.outbox_jobs enable row level security;
create policy outbox_jobs_admin_select on public.outbox_jobs for select to authenticated
using ((select private.is_org_admin(organization_id)));

commit;
