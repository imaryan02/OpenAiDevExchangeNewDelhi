-- Phase: 2.3c — Durable booking side effects and provider work queues
-- Requirements: PAY-01, MSG-01, OBS-01
-- Apply after 20260911001100_phase2_verification_challenge_operations.sql.
-- Recovery: additive columns/tables/functions. Existing appointment history is not rewritten.

begin;

alter table public.outbox_jobs
    add column if not exists lease_token uuid,
    add column if not exists last_error_code text,
    add column if not exists sent_at timestamptz;

create table if not exists public.inbox_events (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid references public.organizations(id) on delete restrict,
    provider text not null check (char_length(trim(provider)) between 1 and 80),
    external_event_id text not null check (char_length(trim(external_event_id)) between 1 and 255),
    event_type text not null check (char_length(trim(event_type)) between 1 and 120),
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'RECEIVED'
        check (status in ('RECEIVED', 'PROCESSING', 'PROCESSED', 'FAILED', 'DEAD_LETTER')),
    attempts integer not null default 0 check (attempts >= 0),
    next_attempt_at timestamptz not null default now(),
    lease_until timestamptz,
    lease_token uuid,
    last_error_code text,
    received_at timestamptz not null default now(),
    processed_at timestamptz,
    unique (provider, external_event_id)
);

create index if not exists inbox_events_dispatch_idx
    on public.inbox_events (status, next_attempt_at)
    where status in ('RECEIVED', 'FAILED', 'PROCESSING');

create index if not exists outbox_jobs_recovery_idx
    on public.outbox_jobs (status, next_attempt_at, lease_until)
    where status in ('PENDING', 'FAILED', 'PROCESSING');

create or replace function private.apply_appointment_lifecycle_side_effects()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if old.status = 'PAYMENT_PENDING' and new.status = 'EXPIRED' then
        update public.payment_attempts
        set status = 'SIMULATED_FAILURE'
        where organization_id = new.organization_id
          and appointment_id = new.id
          and status = 'SIMULATION_PENDING';
    elsif old.status = 'PAYMENT_PENDING' and new.status = 'CONFIRMED' then
        insert into public.outbox_jobs (
            organization_id, job_type, aggregate_id, dedupe_key, payload
        ) values (
            new.organization_id,
            'APPOINTMENT_CONFIRMED',
            new.id,
            'appointment-confirmed:' || new.id::text,
            jsonb_build_object(
                'appointment_id', new.id,
                'booking_reference', new.booking_reference
            )
        ) on conflict (organization_id, dedupe_key) do nothing;
    end if;
    return new;
end;
$$;

revoke all on function private.apply_appointment_lifecycle_side_effects() from public;

drop trigger if exists appointments_lifecycle_side_effects on public.appointments;
create trigger appointments_lifecycle_side_effects
after update of status on public.appointments
for each row
when (old.status is distinct from new.status)
execute function private.apply_appointment_lifecycle_side_effects();

create or replace function public.claim_outbox_jobs(
    p_limit integer default 10,
    p_lease_seconds integer default 60
)
returns setof public.outbox_jobs
language plpgsql
security definer
set search_path = ''
as $$
begin
    if p_limit not between 1 and 100 then
        raise exception 'outbox claim limit must be between 1 and 100';
    end if;
    if p_lease_seconds not between 15 and 300 then
        raise exception 'outbox lease must be between 15 and 300 seconds';
    end if;
    return query
    with claimable as (
        select id
        from public.outbox_jobs
        where (
            status in ('PENDING', 'FAILED') and next_attempt_at <= now()
        ) or (
            status = 'PROCESSING' and lease_until <= now()
        )
        order by next_attempt_at, created_at
        for update skip locked
        limit p_limit
    )
    update public.outbox_jobs job
    set status = 'PROCESSING',
        attempts = job.attempts + 1,
        lease_until = now() + make_interval(secs => p_lease_seconds),
        lease_token = gen_random_uuid(),
        last_error_code = null
    from claimable
    where job.id = claimable.id
    returning job.*;
end;
$$;

create or replace function public.complete_outbox_job(
    p_job_id uuid,
    p_lease_token uuid
)
returns boolean
language sql
security definer
set search_path = ''
as $$
    update public.outbox_jobs
    set status = 'SENT', sent_at = now(), lease_until = null, lease_token = null
    where id = p_job_id and status = 'PROCESSING' and lease_token = p_lease_token
    returning true;
$$;

create or replace function public.fail_outbox_job(
    p_job_id uuid,
    p_lease_token uuid,
    p_error_code text,
    p_retry_seconds integer default 60
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    next_status text;
begin
    if p_retry_seconds not between 5 and 3600 then
        raise exception 'outbox retry delay must be between 5 and 3600 seconds';
    end if;
    update public.outbox_jobs
    set status = case when attempts >= 5 then 'DEAD_LETTER' else 'FAILED' end,
        next_attempt_at = now() + make_interval(secs => p_retry_seconds),
        lease_until = null,
        lease_token = null,
        last_error_code = left(coalesce(nullif(trim(p_error_code), ''), 'UNKNOWN'), 120)
    where id = p_job_id and status = 'PROCESSING' and lease_token = p_lease_token
    returning status into next_status;
    if not found then
        raise exception 'outbox lease is stale or invalid';
    end if;
    return next_status;
end;
$$;

revoke all on function public.claim_outbox_jobs(integer,integer) from public;
revoke all on function public.complete_outbox_job(uuid,uuid) from public;
revoke all on function public.fail_outbox_job(uuid,uuid,text,integer) from public;

alter table public.inbox_events enable row level security;

commit;
