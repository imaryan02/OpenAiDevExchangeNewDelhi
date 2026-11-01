-- Safe, tenant-scoped voice call history. No transcripts, phone numbers, or audio.
begin;

create table if not exists public.voice_observability_calls (
    id uuid primary key,
    organization_id uuid not null references public.organizations(id) on delete restrict,
    provider text not null check (provider in ('VOICELINK', 'TWILIO')),
    provider_call_id text not null check (char_length(provider_call_id) between 1 and 255),
    engine text not null check (engine in ('CHAINED', 'REALTIME')),
    status text not null default 'ACTIVE' check (status in ('ACTIVE', 'ENDED', 'INTERRUPTED', 'FAILED', 'UNKNOWN')),
    started_at timestamptz not null default now(),
    ended_at timestamptz,
    duration_ms integer check (duration_ms is null or duration_ms >= 0),
    last_event_at timestamptz not null default now(),
    event_count integer not null default 0 check (event_count >= 0),
    events_complete boolean not null default true,
    capture_policy jsonb not null default '{"transcripts":false,"recordings":false,"caller_number":false}'::jsonb,
    unique (organization_id, provider, provider_call_id)
);

create index if not exists voice_observability_calls_org_started_idx
    on public.voice_observability_calls (organization_id, started_at desc);

create table if not exists public.voice_observability_events (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    call_id uuid not null references public.voice_observability_calls(id) on delete cascade,
    sequence integer not null check (sequence > 0),
    event_type text not null check (char_length(event_type) between 1 and 80),
    stage text not null check (char_length(stage) between 1 and 40),
    occurred_at timestamptz not null default now(),
    duration_ms integer check (duration_ms is null or duration_ms >= 0),
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    unique (call_id, sequence)
);

create index if not exists voice_observability_events_call_sequence_idx
    on public.voice_observability_events (call_id, sequence);

alter table public.voice_observability_calls enable row level security;
alter table public.voice_observability_events enable row level security;

drop policy if exists voice_observability_calls_booking_staff on public.voice_observability_calls;
create policy voice_observability_calls_booking_staff on public.voice_observability_calls
    for select to authenticated using ((select private.is_org_booking_staff(organization_id)));

drop policy if exists voice_observability_events_booking_staff on public.voice_observability_events;
create policy voice_observability_events_booking_staff on public.voice_observability_events
    for select to authenticated using ((select private.is_org_booking_staff(organization_id)));

revoke all on public.voice_observability_calls, public.voice_observability_events from anon, authenticated;
grant select on public.voice_observability_calls, public.voice_observability_events to authenticated;

commit;
