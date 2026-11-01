-- Phase: 2.2d — Verification challenge lifecycle
-- Requirements: RET-01, RET-02, CHG-01
-- Apply after 20260911001000_phase2_relationship_integrity.sql.
-- Only digests are stored. Raw verification codes must remain in the provider/application boundary.

begin;

with ranked as (
    select id,
           row_number() over (
               partition by organization_id, contact_phone_id
               order by created_at desc, id desc
           ) as position
    from public.verification_challenges
    where status = 'PENDING'
)
update public.verification_challenges challenge
set status = 'CANCELLED'
from ranked
where challenge.id = ranked.id and ranked.position > 1;

create unique index if not exists verification_challenges_one_pending_per_phone_idx
    on public.verification_challenges (organization_id, contact_phone_id)
    where status = 'PENDING';

create or replace function public.issue_verification_challenge(
    p_organization_id uuid,
    p_contact_phone_id uuid,
    p_phone_version integer,
    p_code_digest text,
    p_call_id uuid default null,
    p_ttl_seconds integer default 300
)
returns table (challenge_id uuid, expires_at timestamptz)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
    created_row public.verification_challenges%rowtype;
begin
    if not (select private.is_org_booking_staff(p_organization_id)) then
        raise exception 'booking staff authorization required';
    end if;
    if p_ttl_seconds not between 60 and 900 then
        raise exception 'verification ttl must be between 60 and 900 seconds';
    end if;
    if p_code_digest is null or char_length(p_code_digest) < 32 then
        raise exception 'verification digest is invalid';
    end if;
    perform 1
    from public.contact_phones
    where organization_id = p_organization_id
      and id = p_contact_phone_id
      and version = p_phone_version
      and status = 'ACTIVE'
    for update;
    if not found then
        raise exception 'active saved contact phone required';
    end if;

    update public.verification_challenges
    set status = case when expires_at <= now() then 'EXPIRED' else 'CANCELLED' end
    where organization_id = p_organization_id
      and contact_phone_id = p_contact_phone_id
      and status = 'PENDING';

    insert into public.verification_challenges (
        organization_id, call_id, contact_phone_id, phone_version,
        code_digest, expires_at
    ) values (
        p_organization_id, p_call_id, p_contact_phone_id, p_phone_version,
        p_code_digest, now() + make_interval(secs => p_ttl_seconds)
    ) returning * into created_row;

    return query select created_row.id, created_row.expires_at;
end;
$$;

create or replace function public.verify_verification_challenge(
    p_organization_id uuid,
    p_challenge_id uuid,
    p_code_digest text,
    p_verified_seconds integer default 600
)
returns table (
    verified boolean,
    challenge_status text,
    attempts_remaining integer,
    verified_until timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
    challenge_row public.verification_challenges%rowtype;
    next_attempt_count integer;
begin
    if not (select private.is_org_booking_staff(p_organization_id)) then
        raise exception 'booking staff authorization required';
    end if;
    if p_verified_seconds not between 60 and 1800 then
        raise exception 'verified window must be between 60 and 1800 seconds';
    end if;

    select * into challenge_row
    from public.verification_challenges
    where organization_id = p_organization_id and id = p_challenge_id
    for update;
    if not found then
        raise exception 'verification challenge not found';
    end if;

    if challenge_row.status <> 'PENDING' then
        return query select false, challenge_row.status,
            greatest(0, 5 - challenge_row.attempt_count), challenge_row.verified_until;
        return;
    end if;
    if challenge_row.expires_at <= now() then
        update public.verification_challenges
        set status = 'EXPIRED'
        where organization_id = p_organization_id and id = p_challenge_id
        returning * into challenge_row;
        return query select false, challenge_row.status,
            greatest(0, 5 - challenge_row.attempt_count), challenge_row.verified_until;
        return;
    end if;

    if challenge_row.code_digest = p_code_digest then
        update public.verification_challenges
        set status = 'VERIFIED', consumed_at = now(),
            verified_until = now() + make_interval(secs => p_verified_seconds)
        where organization_id = p_organization_id and id = p_challenge_id
        returning * into challenge_row;
        return query select true, challenge_row.status,
            greatest(0, 5 - challenge_row.attempt_count), challenge_row.verified_until;
        return;
    end if;

    next_attempt_count := challenge_row.attempt_count + 1;
    update public.verification_challenges
    set attempt_count = next_attempt_count,
        status = case when next_attempt_count >= 5 then 'LOCKED' else 'PENDING' end
    where organization_id = p_organization_id and id = p_challenge_id
    returning * into challenge_row;
    return query select false, challenge_row.status,
        greatest(0, 5 - challenge_row.attempt_count), challenge_row.verified_until;
end;
$$;

create or replace function public.expire_verification_challenges()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    expired_count integer;
begin
    update public.verification_challenges
    set status = 'EXPIRED'
    where status = 'PENDING' and expires_at <= now();
    get diagnostics expired_count = row_count;
    return expired_count;
end;
$$;

revoke all on function public.issue_verification_challenge(uuid,uuid,integer,text,uuid,integer) from public;
revoke all on function public.verify_verification_challenge(uuid,uuid,text,integer) from public;
revoke all on function public.expire_verification_challenges() from public;
grant execute on function public.issue_verification_challenge(uuid,uuid,integer,text,uuid,integer) to authenticated;
grant execute on function public.verify_verification_challenge(uuid,uuid,text,integer) to authenticated;

commit;
