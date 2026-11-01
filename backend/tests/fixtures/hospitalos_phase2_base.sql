-- Minimal isolated PostgreSQL fixture for syntax and constraint checks.
create role anon;
create role authenticated;
create schema private;
create function private.prevent_audit_mutation() returns trigger
language plpgsql as $$ begin raise exception 'immutable'; end; $$;
create function private.is_org_member(uuid) returns boolean
language sql as $$ select true $$;
create function private.is_org_admin(uuid) returns boolean
language sql as $$ select true $$;
create table public.organizations (
    id uuid primary key, name text not null, status text not null
);
create table public.locations (
    id uuid primary key, organization_id uuid not null references public.organizations(id),
    name text not null, active boolean not null,
    unique (organization_id,id)
);
create table public.organization_users (
    organization_id uuid not null references public.organizations(id),
    auth_user_id uuid not null, role text not null, active boolean not null
);
create table public.audit_events (
    organization_id uuid, actor_type text, actor_id uuid, action text,
    entity_type text, entity_id uuid, safe_change_summary jsonb
);
insert into public.organizations values
  ('c562e817-bfae-4428-904d-15ac84b9acd7','Geeta Medicine','ACTIVE');
insert into public.locations values
  ('7799adcd-99b2-4123-95ed-078847118fde',
   'c562e817-bfae-4428-904d-15ac84b9acd7','Main Branch',true);
