-- Phase 2 corrective migration: deterministic caller/patient relationship integrity.
-- One active E.164 mobile belongs to one contact per organization (existing index).
-- One contact may represent/book for many patients through explicit relationship links.

begin;

update public.patient_contacts
set relationship = case upper(trim(relationship))
    when 'SELF' then 'SELF'
    when 'MOTHER' then 'MOTHER'
    when 'FATHER' then 'FATHER'
    when 'SPOUSE' then 'SPOUSE'
    when 'CHILD' then 'CHILD'
    else 'OTHER'
end;

alter table public.patient_contacts
    drop constraint if exists patient_contacts_relationship_check;

alter table public.patient_contacts
    add constraint patient_contacts_relationship_check
    check (relationship in ('SELF', 'MOTHER', 'FATHER', 'SPOUSE', 'CHILD', 'OTHER'));

do $$
begin
    if exists (
        select 1
        from public.patient_contacts
        where relationship_status = 'RECORDED' and relationship = 'SELF'
        group by organization_id, contact_id
        having count(*) > 1
    ) then
        raise exception 'A caller has more than one active SELF patient; review those records before applying this migration.';
    end if;
end
$$;

create unique index if not exists patient_contacts_one_self_per_contact_idx
    on public.patient_contacts (organization_id, contact_id)
    where relationship_status = 'RECORDED' and relationship = 'SELF';

commit;

select jsonb_build_object(
    'phase_2_relationship_integrity', jsonb_build_object(
        'active_phone_unique_per_organization', exists (
            select 1 from pg_indexes
            where schemaname='public' and tablename='contact_phones'
              and indexname='contact_phones_one_active_phone_per_tenant_idx'
        ),
        'one_self_patient_per_caller', exists (
            select 1 from pg_indexes
            where schemaname='public' and tablename='patient_contacts'
              and indexname='patient_contacts_one_self_per_contact_idx'
        ),
        'allowed_relationships', jsonb_build_array(
            'SELF', 'MOTHER', 'FATHER', 'SPOUSE', 'CHILD', 'OTHER'
        )
    )
) as verification;
