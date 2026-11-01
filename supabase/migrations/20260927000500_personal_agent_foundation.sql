-- Personal AI Phase 2. Additive, owner-scoped; no clinic records or grants changed.
-- Depends on Supabase auth.users. Apply once and run matching verification file.
-- Recovery: disable PERSONAL_AGENT_ENABLED and retain these tables; do not drop history.
-- Reviewed against owner-supplied 30-table context snapshot: no name collisions.
-- The snapshot is not executable SQL. This file changes only new personal_agent_* objects.
begin;

create table public.personal_agent_profiles (
    owner_id uuid primary key references auth.users(id),
    phone_e164 text not null unique check (phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
    timezone text not null default 'Asia/Kolkata',
    language text not null default 'adaptive' check (language in ('adaptive','english','hinglish')),
    mode text not null default 'receptionist' check (mode in ('receptionist','personal_agent')),
    whatsapp_fallback boolean not null default false,
    generation integer not null default 1 check (generation > 0),
    updated_at timestamptz not null default now()
);

create table public.personal_agent_tasks (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references public.personal_agent_profiles(owner_id),
    title text not null check (length(title) between 1 and 200),
    description text not null default '' check (length(description) <= 1000),
    status text not null default 'pending' check (status in ('pending','completed')),
    due_at timestamptz,
    completed_at timestamptz,
    deleted_at timestamptz,
    version integer not null default 1 check (version > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (owner_id, id)
);

create table public.personal_agent_followups (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references public.personal_agent_profiles(owner_id),
    generation integer not null check (generation > 0),
    title text not null check (length(title) between 1 and 200),
    context text not null default '' check (length(context) <= 1000),
    task_snapshot jsonb not null default '[]' check (jsonb_typeof(task_snapshot)='array'),
    source_call_id uuid,
    status text not null default 'scheduled' check (status in
        ('pending','scheduled','in_progress','awaiting_acknowledgment','resolved','cancelled','needs_attention')),
    next_action text check (next_action in ('call','message')),
    next_action_at timestamptz,
    call_attempts integer not null default 0 check (call_attempts >= 0),
    resolution text,
    version integer not null default 1 check (version > 0),
    lease_token uuid,
    lease_until timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (owner_id, id)
);

create table public.personal_agent_calls (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references public.personal_agent_profiles(owner_id),
    generation integer not null,
    provider text not null check (provider in ('voicelink','twilio')),
    provider_call_id text not null,
    direction text not null check (direction in ('inbound','outbound')),
    agent_mode text not null default 'personal_agent' check (agent_mode='personal_agent'),
    followup_id uuid,
    status text not null default 'active' check (status in ('active','ended','failed','expired')),
    heartbeat_at timestamptz not null default now(),
    started_at timestamptz not null default now(),
    ended_at timestamptz,
    unique (provider, provider_call_id),
    unique (owner_id, id),
    foreign key (owner_id, followup_id) references public.personal_agent_followups(owner_id,id)
);

alter table public.personal_agent_followups add constraint personal_agent_source_call_fk
    foreign key (owner_id, source_call_id) references public.personal_agent_calls(owner_id,id);

create table public.personal_agent_attempts (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null,
    followup_id uuid not null,
    generation integer not null,
    event_version integer not null,
    provider_call_id text unique,
    status text not null default 'queued' check (status in
        ('queued','submitting','accepted','ringing','in-progress','completed','busy','no-answer','failed','canceled','unknown')),
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    error_code text,
    foreign key (owner_id, followup_id) references public.personal_agent_followups(owner_id,id)
);

create table public.personal_agent_messages (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null,
    followup_id uuid not null,
    generation integer not null,
    event_version integer not null,
    body text not null check (length(body) between 1 and 1600),
    provider_message_id text unique,
    status text not null default 'queued' check (status in
        ('queued','submitting','accepted','sending','sent','delivered','read','failed','undelivered','unknown','canceled')),
    error_code text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (owner_id, followup_id) references public.personal_agent_followups(owner_id,id)
);

create table public.personal_agent_memory (
    id bigint generated always as identity primary key,
    owner_id uuid not null,
    call_id uuid not null,
    generation integer not null,
    source_id text not null,
    speaker text not null check (speaker in ('caller','assistant')),
    content text not null check (length(content) <= 2000),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    unique (call_id,source_id,speaker),
    foreign key (owner_id,call_id) references public.personal_agent_calls(owner_id,id)
);

create table public.personal_agent_events (
    id bigint generated always as identity primary key,
    owner_id uuid not null references public.personal_agent_profiles(owner_id),
    generation integer not null,
    event_type text not null,
    description text not null,
    metadata jsonb not null default '{}' check (jsonb_typeof(metadata)='object'),
    call_id uuid,
    followup_id uuid,
    created_at timestamptz not null default now(),
    foreign key (owner_id,call_id) references public.personal_agent_calls(owner_id,id),
    foreign key (owner_id,followup_id) references public.personal_agent_followups(owner_id,id)
);

create table public.personal_agent_tool_results (
    call_id uuid not null,
    owner_id uuid not null,
    request_id text not null,
    input_hash text not null,
    result jsonb not null,
    created_at timestamptz not null default now(),
    primary key (call_id,request_id),
    foreign key (owner_id,call_id) references public.personal_agent_calls(owner_id,id)
);

create index personal_agent_tasks_owner on public.personal_agent_tasks(owner_id,created_at);
create index personal_agent_due on public.personal_agent_followups(next_action_at)
    where status='scheduled';
create index personal_agent_calls_active on public.personal_agent_calls(owner_id,heartbeat_at)
    where status='active';
create index personal_agent_attempt_event on public.personal_agent_attempts(owner_id,followup_id);
create index personal_agent_message_event on public.personal_agent_messages(owner_id,followup_id);
create index personal_agent_memory_owner on public.personal_agent_memory(owner_id,created_at desc);
create index personal_agent_memory_expiry on public.personal_agent_memory(expires_at);
create index personal_agent_events_owner on public.personal_agent_events(owner_id,id desc);

-- Read policies only. Mutations are server-controlled, including mode and destinations.
do $$
declare table_name text;
begin
    foreach table_name in array array[
        'personal_agent_profiles','personal_agent_tasks','personal_agent_followups',
        'personal_agent_calls','personal_agent_attempts','personal_agent_messages',
        'personal_agent_memory','personal_agent_events','personal_agent_tool_results'
    ] loop
        execute format('alter table public.%I enable row level security',table_name);
        execute format('revoke all on public.%I from anon, authenticated',table_name);
        execute format('grant select on public.%I to authenticated',table_name);
        execute format('create policy personal_owner_read on public.%I for select to authenticated using (owner_id = auth.uid())',table_name);
    end loop;
end $$;
commit;
