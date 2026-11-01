-- Run after creating a demo user in Supabase Dashboard -> Authentication -> Users.
-- Replace the UUID below with that user's ID. Do not put an email or password here.

do $$
declare
    v_user_id uuid := 'REPLACE_WITH_AUTH_USER_UUID'::uuid;
    v_organization_id uuid;
begin
    if not exists (select 1 from auth.users where id = v_user_id) then
        raise exception 'Auth user % does not exist', v_user_id;
    end if;
    select id into v_organization_id
    from public.organizations
    where name = 'Geeta Medicine'
    limit 1;
    if v_organization_id is null then
        raise exception 'Geeta Medicine seed was not found';
    end if;
    insert into public.organization_users (organization_id, auth_user_id, role, active)
    values (v_organization_id, v_user_id, 'ORG_ADMIN', true)
    on conflict (organization_id, auth_user_id)
    do update set role = excluded.role, active = true;
end;
$$;

select jsonb_build_object(
  'organization', 'Geeta Medicine',
  'admin_memberships', (
    select count(*)
    from public.organization_users memberships
    join public.organizations organizations on organizations.id = memberships.organization_id
    where organizations.name = 'Geeta Medicine'
      and memberships.role = 'ORG_ADMIN'
      and memberships.active
  )
) as geeta_admin_setup;
