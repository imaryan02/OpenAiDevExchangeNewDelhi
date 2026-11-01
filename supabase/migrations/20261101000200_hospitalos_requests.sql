-- HospitalOS Phase 2: synthetic pre-arrival requests, bounded holds, and event history.
-- Owner-run after 20261101000100. This migration does not create patient records.
-- Recovery: disable HospitalOS routes; retain request and event rows for investigation.
begin;

create table public.hospitalos_cases (
    id uuid primary key,
    tracking_token_hash text not null unique check (tracking_token_hash ~ '^[a-f0-9]{64}$'),
    origin text not null check (origin in ('CENTRAL_DELHI','NORTH_DELHI','EAST_DELHI')),
    preference text not null check (preference in ('ANY','AFFORDABLE','PRIVATE')),
    requirement text not null check (requirement in ('GENERAL','ICU','TRAUMA','PEDIATRIC','OBSTETRIC')),
    audience text not null check (audience in ('PATIENT','AMBULANCE')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    eta_minutes smallint check (eta_minutes between 1 and 240),
    constraint hospitalos_patient_requirement_check check (audience='AMBULANCE' or requirement='GENERAL')
);

create table public.hospitalos_requests (
    id uuid primary key default gen_random_uuid(),
    case_id uuid not null unique references public.hospitalos_cases(id) on delete restrict,
    facility_id uuid not null references public.hospitalos_facilities(id) on delete restrict,
    organization_id uuid not null references public.organizations(id) on delete restrict,
    status text not null default 'PENDING' check (status in
      ('PENDING','ACCEPTED','DECLINED','EXPIRED','WITHDRAWN','HOLD_CONFLICT')),
    version integer not null default 1 check (version > 0),
    deadline_at timestamptz not null,
    created_at timestamptz not null default now(),
    decided_at timestamptz,
    decided_by uuid,
    decision_key uuid unique,
    arrival_note text check (length(arrival_note) <= 240),
    updated_at timestamptz not null default now(),
    constraint hospitalos_decision_actor_check check
      (status not in ('ACCEPTED','DECLINED','HOLD_CONFLICT') or decided_by is not null)
);

create index hospitalos_requests_inbox_idx on public.hospitalos_requests
    (organization_id,status,created_at desc);
create index hospitalos_requests_deadline_idx on public.hospitalos_requests
    (deadline_at) where status='PENDING';

create table public.hospitalos_holds (
    id uuid primary key default gen_random_uuid(),
    request_id uuid not null unique references public.hospitalos_requests(id) on delete restrict,
    facility_id uuid not null references public.hospitalos_facilities(id) on delete restrict,
    ed_units smallint not null default 1 check (ed_units=1),
    icu_units smallint not null default 0 check (icu_units in (0,1)),
    status text not null default 'ACTIVE' check (status in ('ACTIVE','RELEASED','EXPIRED')),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    ended_at timestamptz
);
create index hospitalos_holds_capacity_idx on public.hospitalos_holds
    (facility_id,status,expires_at);

create table public.hospitalos_events (
    id bigint generated always as identity primary key,
    case_id uuid not null references public.hospitalos_cases(id) on delete restrict,
    request_id uuid references public.hospitalos_requests(id) on delete restrict,
    organization_id uuid references public.organizations(id) on delete restrict,
    event_type text not null check (event_type in
      ('CASE_CREATED','ACCEPTANCE_REQUESTED','REQUEST_EXPIRED','REQUEST_DECLINED',
       'HOSPITAL_ACCEPTED','RESOURCE_REVALIDATED','HOLD_CREATED','HOLD_CONFLICT',
       'REQUEST_WITHDRAWN','ETA_UPDATED','AGENT_TASK_CREATED','TASK_COMPLETED',
       'HUMAN_REVIEW_REQUESTED')),
    actor_type text not null check (actor_type in ('PUBLIC','USER','SYSTEM')),
    actor_id uuid,
    detail jsonb not null default '{}'::jsonb,
    occurred_at timestamptz not null default now()
);
create index hospitalos_events_case_idx on public.hospitalos_events (case_id,id);
create trigger hospitalos_events_immutable before update or delete on public.hospitalos_events
    for each row execute function private.prevent_audit_mutation();

alter table public.hospitalos_cases enable row level security;
alter table public.hospitalos_requests enable row level security;
alter table public.hospitalos_holds enable row level security;
alter table public.hospitalos_events enable row level security;
revoke all on public.hospitalos_cases, public.hospitalos_requests,
    public.hospitalos_holds, public.hospitalos_events from anon, authenticated;

commit;
