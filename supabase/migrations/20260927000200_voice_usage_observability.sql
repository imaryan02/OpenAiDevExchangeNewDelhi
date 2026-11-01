-- Provider-reported voice usage. No pricing estimates or user content are stored.
begin;

create table if not exists public.voice_observability_usage (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete restrict,
    call_id uuid not null references public.voice_observability_calls(id) on delete cascade,
    provider text not null check (provider in ('OPENAI')),
    engine text not null check (engine in ('CHAINED', 'REALTIME')),
    operation text not null check (
        operation in ('transcription', 'agent_response', 'realtime_response')
    ),
    model text not null check (char_length(model) between 1 and 120),
    request_id text not null check (char_length(request_id) between 1 and 160),
    identity_source text not null check (identity_source in ('provider', 'local')),
    usage_type text not null check (usage_type in ('tokens', 'duration')),
    input_tokens bigint check (input_tokens is null or input_tokens >= 0),
    output_tokens bigint check (output_tokens is null or output_tokens >= 0),
    total_tokens bigint check (total_tokens is null or total_tokens >= 0),
    input_audio_tokens bigint check (input_audio_tokens is null or input_audio_tokens >= 0),
    output_audio_tokens bigint check (output_audio_tokens is null or output_audio_tokens >= 0),
    cached_input_tokens bigint check (cached_input_tokens is null or cached_input_tokens >= 0),
    duration_seconds numeric(12, 3) check (duration_seconds is null or duration_seconds >= 0),
    pricing_version text,
    estimated_cost_microusd bigint check (
        estimated_cost_microusd is null or estimated_cost_microusd >= 0
    ),
    observed_at timestamptz not null default now(),
    unique (organization_id, call_id, provider, request_id),
    check (
        (usage_type = 'tokens' and (input_tokens is not null or output_tokens is not null))
        or (usage_type = 'duration' and duration_seconds is not null)
    )
);

create index if not exists voice_observability_usage_call_idx
    on public.voice_observability_usage (organization_id, call_id, observed_at);

alter table public.voice_observability_usage enable row level security;
drop policy if exists voice_observability_usage_booking_staff
    on public.voice_observability_usage;
create policy voice_observability_usage_booking_staff
    on public.voice_observability_usage for select to authenticated
    using ((select private.is_org_booking_staff(organization_id)));

revoke all on public.voice_observability_usage from anon, authenticated;
grant select on public.voice_observability_usage to authenticated;

commit;
