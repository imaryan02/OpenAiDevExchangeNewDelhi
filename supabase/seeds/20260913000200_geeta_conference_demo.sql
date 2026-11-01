-- Idempotent Geeta Medicine conference dataset.
-- Azure must use VOICE_ORGANIZATION_ID=c562e817-bfae-4428-904d-15ac84b9acd7.
-- Caller mobile: +918529586946. VoiceLink DID: +919429397279 (not stored as caller).

begin;

do $$
declare
    v_org uuid := 'c562e817-bfae-4428-904d-15ac84b9acd7'::uuid;
    v_location uuid;
    v_general uuid;
    v_gynae uuid;
    v_pediatrics uuid;
    v_amit_doctor uuid;
    v_sweta_doctor uuid;
    v_amit_assignment uuid;
    v_sweta_assignment uuid;
    v_contact uuid;
    v_phone uuid;
    v_self_patient uuid;
    v_mother_patient uuid;
    v_day date;
    v_start timestamptz;
    v_end timestamptz;
begin
    insert into public.organizations (id, name, organization_type, timezone, status)
    values (v_org, 'Geeta Medicine', 'CLINIC', 'Asia/Kolkata', 'ACTIVE')
    on conflict (id) do update
    set name = excluded.name,
        organization_type = excluded.organization_type,
        timezone = excluded.timezone,
        status = excluded.status;

    insert into public.locations (organization_id, name, address, timezone, active)
    values (v_org, 'Main Branch', 'Sector 14, Gurugram, Haryana', 'Asia/Kolkata', true)
    on conflict (organization_id, name) do update
    set address = excluded.address, timezone = excluded.timezone, active = true
    returning id into v_location;

    insert into public.departments (organization_id, name, active)
    values (v_org, 'General Medicine', true)
    on conflict (organization_id, name) do update set active = true
    returning id into v_general;

    insert into public.departments (organization_id, name, active)
    values (v_org, 'Gynaecology', true)
    on conflict (organization_id, name) do update set active = true
    returning id into v_gynae;

    insert into public.departments (organization_id, name, active)
    values (v_org, 'Pediatrics', true)
    on conflict (organization_id, name) do update set active = true
    returning id into v_pediatrics;

    select id into v_amit_doctor from public.doctors where canonical_name = 'Dr Amit Kumar' limit 1;
    if v_amit_doctor is null then
        insert into public.doctors (canonical_name, qualifications)
        values ('Dr Amit Kumar', array['MBBS', 'MD (Internal Medicine)'])
        returning id into v_amit_doctor;
    else
        update public.doctors set qualifications = array['MBBS', 'MD (Internal Medicine)'], active = true
        where id = v_amit_doctor;
    end if;

    select id into v_sweta_doctor from public.doctors where canonical_name = 'Dr Sweta Gupta' limit 1;
    if v_sweta_doctor is null then
        insert into public.doctors (canonical_name, qualifications)
        values ('Dr Sweta Gupta', array['MBBS', 'MS (OB-GYN)'])
        returning id into v_sweta_doctor;
    else
        update public.doctors set qualifications = array['MBBS', 'MS (OB-GYN)'], active = true
        where id = v_sweta_doctor;
    end if;

    insert into public.doctor_assignments
        (organization_id, doctor_id, location_id, department_id, display_name, fee_minor, currency, active)
    values (v_org, v_amit_doctor, v_location, v_general, 'Dr Amit Kumar', 50000, 'INR', true)
    on conflict (organization_id, doctor_id, location_id, department_id) do update
    set display_name = excluded.display_name, fee_minor = excluded.fee_minor, active = true
    returning id into v_amit_assignment;

    insert into public.doctor_assignments
        (organization_id, doctor_id, location_id, department_id, display_name, fee_minor, currency, active)
    values (v_org, v_sweta_doctor, v_location, v_gynae, 'Dr Sweta Gupta', 70000, 'INR', true)
    on conflict (organization_id, doctor_id, location_id, department_id) do update
    set display_name = excluded.display_name, fee_minor = excluded.fee_minor, active = true
    returning id into v_sweta_assignment;

    -- Materialize searchable token sessions for the next fourteen clinic-local days.
    for v_day in
        select ((now() at time zone 'Asia/Kolkata')::date + offset_number)::date
        from generate_series(1, 14) as offset_number
    loop
        v_start := (v_day + time '10:00') at time zone 'Asia/Kolkata';
        v_end := (v_day + time '12:00') at time zone 'Asia/Kolkata';
        insert into public.appointment_sessions
            (organization_id, assignment_id, doctor_id, starts_at, ends_at, timezone,
             booking_mode, max_patients, booking_cutoff_minutes, status)
        values (v_org, v_amit_assignment, v_amit_doctor, v_start, v_end, 'Asia/Kolkata',
                'SESSION_TOKEN', 20, 15, 'SCHEDULED')
        on conflict (organization_id, assignment_id, starts_at) do update
        set ends_at = excluded.ends_at, max_patients = 20, status = 'SCHEDULED';

        v_start := (v_day + time '16:00') at time zone 'Asia/Kolkata';
        v_end := (v_day + time '18:00') at time zone 'Asia/Kolkata';
        insert into public.appointment_sessions
            (organization_id, assignment_id, doctor_id, starts_at, ends_at, timezone,
             booking_mode, max_patients, booking_cutoff_minutes, status)
        values (v_org, v_sweta_assignment, v_sweta_doctor, v_start, v_end, 'Asia/Kolkata',
                'SESSION_TOKEN', 20, 15, 'SCHEDULED')
        on conflict (organization_id, assignment_id, starts_at) do update
        set ends_at = excluded.ends_at, max_patients = 20, status = 'SCHEDULED';
    end loop;

    select c.id, cp.id into v_contact, v_phone
    from public.contacts c
    join public.contact_phones cp
      on cp.organization_id = c.organization_id and cp.contact_id = c.id
    where c.organization_id = v_org
      and cp.phone_e164 = '+918529586946'
      and cp.status = 'ACTIVE'
    limit 1;

    if v_contact is null then
        select id into v_contact
        from public.contacts
        where organization_id = v_org and display_name = 'Aryan Gupta' and status = 'ACTIVE'
        order by created_at limit 1;
    end if;
    if v_contact is null then
        insert into public.contacts (organization_id, display_name, name_source, status)
        values (v_org, 'Aryan Gupta', 'STATED', 'ACTIVE') returning id into v_contact;
    else
        update public.contacts set display_name = 'Aryan Gupta', status = 'ACTIVE' where id = v_contact;
    end if;

    -- Disable the earlier erroneous use of the VoiceLink DID as caller identity.
    update public.contact_phones
    set status = 'DISABLED', version = version + 1
    where organization_id = v_org
      and phone_e164 = '+919429397279'
      and status = 'ACTIVE';

    select id into v_phone from public.contact_phones
    where organization_id = v_org and phone_e164 = '+918529586946' and status = 'ACTIVE';
    if v_phone is null then
        insert into public.contact_phones
            (organization_id, contact_id, phone_e164, status, last_verified_at)
        values (v_org, v_contact, '+918529586946', 'ACTIVE', now())
        returning id into v_phone;
    end if;

    select p.id into v_self_patient
    from public.patients p
    join public.patient_contacts pc
      on pc.organization_id = p.organization_id and pc.patient_id = p.id
    where p.organization_id = v_org and pc.contact_id = v_contact
      and pc.relationship = 'SELF' and pc.relationship_status = 'RECORDED'
    limit 1;
    if v_self_patient is null then
        insert into public.patients (organization_id, display_name, status)
        values (v_org, 'Aryan Gupta', 'ACTIVE') returning id into v_self_patient;
        insert into public.patient_contacts
            (organization_id, patient_id, contact_id, relationship, relationship_status)
        values (v_org, v_self_patient, v_contact, 'SELF', 'RECORDED');
    else
        update public.patients set display_name = 'Aryan Gupta', status = 'ACTIVE'
        where id = v_self_patient;
    end if;

    select p.id into v_mother_patient
    from public.patients p
    join public.patient_contacts pc
      on pc.organization_id = p.organization_id and pc.patient_id = p.id
    where p.organization_id = v_org and pc.contact_id = v_contact
      and pc.relationship = 'MOTHER' and pc.relationship_status = 'RECORDED'
    limit 1;
    if v_mother_patient is null then
        insert into public.patients (organization_id, display_name, status)
        values (v_org, 'Bibha Gupta', 'ACTIVE') returning id into v_mother_patient;
        insert into public.patient_contacts
            (organization_id, patient_id, contact_id, relationship, relationship_status)
        values (v_org, v_mother_patient, v_contact, 'MOTHER', 'RECORDED');
    else
        update public.patients set display_name = 'Bibha Gupta', status = 'ACTIVE'
        where id = v_mother_patient;
    end if;
end;
$$;

commit;

select jsonb_build_object(
    'organization', organization.name,
    'organization_id', organization.id,
    'caller_phone', '+918529586946',
    'voicelink_number', '+919429397279',
    'doctors', (
        select jsonb_agg(assignment.display_name order by assignment.display_name)
        from public.doctor_assignments assignment
        where assignment.organization_id = organization.id and assignment.active
    ),
    'future_sessions', (
        select count(*) from public.appointment_sessions session
        where session.organization_id = organization.id
          and session.starts_at > now()
          and session.status in ('SCHEDULED', 'OPEN')
    )
) as conference_demo
from public.organizations organization
where organization.id = 'c562e817-bfae-4428-904d-15ac84b9acd7'::uuid;
