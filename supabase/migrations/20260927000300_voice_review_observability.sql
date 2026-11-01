-- Additive call review support. Conversation capture remains disabled in application defaults.
begin;

create unique index if not exists voice_observability_calls_org_id_idx
    on public.voice_observability_calls (organization_id, id);

create table if not exists public.voice_observability_messages (
    sequence bigint generated always as identity primary key,
    organization_id uuid not null references public.organizations(id),
    call_id uuid not null,
    speaker text not null check (speaker in ('caller', 'assistant')),
    content text not null check (char_length(content) between 1 and 16000),
    evidence text not null check (evidence in
        ('transcription', 'generated_text', 'generated_audio_transcript')),
    source_id text not null check (char_length(source_id) between 1 and 255),
    occurred_at timestamptz not null,
    elapsed_ms integer not null check (elapsed_ms >= 0),
    expires_at timestamptz not null,
    truncated boolean not null default false,
    foreign key (organization_id, call_id)
        references public.voice_observability_calls(organization_id, id),
    unique (organization_id, call_id, speaker, source_id)
);
create index if not exists voice_messages_call_sequence_idx
    on public.voice_observability_messages(organization_id, call_id, sequence);
create index if not exists voice_messages_expiry_idx
    on public.voice_observability_messages(expires_at);

create table if not exists public.voice_observability_content_access (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null,
    call_id uuid not null,
    user_id uuid not null,
    accessed_at timestamptz not null default now(),
    message_count integer not null check (message_count >= 0),
    foreign key (organization_id, call_id)
        references public.voice_observability_calls(organization_id, id)
);

create table if not exists public.voice_observability_attempts (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id),
    status text not null check (status in
        ('ACCEPTED', 'CONFIGURATION_INCOMPLETE', 'INVALID_TOKEN', 'FAILED')),
    occurred_at timestamptz not null
);
create index if not exists voice_attempts_org_time_idx
    on public.voice_observability_attempts(organization_id, occurred_at desc);

alter table public.voice_observability_messages enable row level security;
alter table public.voice_observability_content_access enable row level security;
alter table public.voice_observability_attempts enable row level security;
-- Text is read through the authorized, audited backend endpoint, not directly via PostgREST.
revoke all on public.voice_observability_messages,
    public.voice_observability_content_access from anon, authenticated;
revoke all on sequence public.voice_observability_messages_sequence_seq from anon, authenticated;
revoke all on public.voice_observability_attempts from anon, authenticated;
grant select on public.voice_observability_attempts to authenticated;
drop policy if exists voice_attempts_staff on public.voice_observability_attempts;
create policy voice_attempts_staff on public.voice_observability_attempts
    for select to authenticated using ((select private.is_org_booking_staff(organization_id)));

commit;
