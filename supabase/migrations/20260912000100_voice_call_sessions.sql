-- Durable, versioned session and operation ledger for telephone voice calls.
-- Additive migration: existing appointments and booking idempotency are unchanged.

begin;

create table if not exists public.voice_call_sessions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    provider_call_id text not null check (char_length(trim(provider_call_id)) between 1 and 255),
    caller_phone_e164 text not null check (char_length(trim(caller_phone_e164)) between 8 and 20),
    owner_token uuid not null default gen_random_uuid(),
    status text not null default 'ACTIVE'
        check (status in ('ACTIVE', 'CLOSING', 'ENDED', 'EXPIRED')),
    state_version integer not null default 0 check (state_version >= 0),
    state jsonb not null default '{}'::jsonb,
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    ended_at timestamptz,
    unique (organization_id, provider_call_id)
);

create index if not exists voice_call_sessions_active_expiry_idx
    on public.voice_call_sessions (status, expires_at)
    where status = 'ACTIVE';

create table if not exists public.voice_operation_records (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    voice_call_session_id uuid not null references public.voice_call_sessions(id) on delete restrict,
    operation_id uuid not null,
    operation_type text not null check (operation_type in ('BOOK', 'CANCEL', 'RESCHEDULE')),
    proposal_version text not null check (char_length(trim(proposal_version)) between 1 and 255),
    idempotency_key text not null check (char_length(trim(idempotency_key)) between 16 and 255),
    status text not null default 'PROPOSED'
        check (status in ('PROPOSED', 'READBACK_COMPLETED', 'APPROVED', 'COMMITTED', 'FAILED', 'UNKNOWN')),
    result jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    committed_at timestamptz,
    unique (organization_id, operation_id),
    unique (organization_id, idempotency_key)
);

create index if not exists voice_operation_records_session_status_idx
    on public.voice_operation_records (voice_call_session_id, status, created_at desc);

drop trigger if exists voice_call_sessions_set_updated_at on public.voice_call_sessions;
create trigger voice_call_sessions_set_updated_at before update on public.voice_call_sessions
for each row execute function private.set_updated_at();

drop trigger if exists voice_operation_records_set_updated_at on public.voice_operation_records;
create trigger voice_operation_records_set_updated_at before update on public.voice_operation_records
for each row execute function private.set_updated_at();

alter table public.voice_call_sessions enable row level security;
alter table public.voice_operation_records enable row level security;

drop policy if exists voice_call_sessions_booking_staff on public.voice_call_sessions;
create policy voice_call_sessions_booking_staff on public.voice_call_sessions for all to authenticated
using ((select private.is_org_booking_staff(organization_id)))
with check ((select private.is_org_booking_staff(organization_id)));

drop policy if exists voice_operation_records_booking_staff on public.voice_operation_records;
create policy voice_operation_records_booking_staff on public.voice_operation_records for all to authenticated
using ((select private.is_org_booking_staff(organization_id)))
with check ((select private.is_org_booking_staff(organization_id)));

commit;
