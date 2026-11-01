-- Phase: 2.2d — Immutable booking quote and explicit consent snapshots
-- Requirements: BKG-01
-- Apply after 20260911001200_phase2_durable_booking_side_effects.sql.

begin;

create or replace function public.create_simulated_appointment_hold(
    p_organization_id uuid, p_patient_id uuid, p_booked_by_contact_id uuid,
    p_notification_contact_phone_id uuid, p_assignment_id uuid, p_session_id uuid,
    p_slot_id uuid, p_source text, p_idempotency_key text, p_request_hash text,
    p_consent_confirmed boolean, p_consent_language text, p_consent_channel text,
    p_hold_seconds integer default 600
)
returns table (appointment_id uuid, booking_reference text, status text, hold_expires_at timestamptz)
language plpgsql security definer set search_path = ''
as $$
#variable_conflict use_column
declare
    session_row public.appointment_sessions%rowtype;
    assignment_row public.doctor_assignments%rowtype;
    existing_record public.idempotency_records%rowtype;
    appointment_row public.appointments%rowtype;
    occupancy integer;
    now_at timestamptz := now();
    quoted_starts_at timestamptz;
    quoted_ends_at timestamptz;
    patient_name text;
    contact_name text;
    notification_phone text;
    location_name text;
    quote_version text;
begin
    if not (select private.is_org_booking_staff(p_organization_id)) then
        raise exception 'booking staff authorization required';
    end if;
    if p_hold_seconds not between 60 and 1800 then
        raise exception 'hold duration must be between 60 and 1800 seconds';
    end if;
    if p_consent_confirmed is distinct from true then
        raise exception 'explicit booking consent is required';
    end if;
    if p_consent_language not in ('en', 'hi', 'en-IN', 'hi-IN') then
        raise exception 'supported consent language is required';
    end if;
    if p_consent_channel not in ('STAFF_UI', 'AI_TEXT', 'AI_VOICE') then
        raise exception 'supported consent channel is required';
    end if;
    if (p_source in ('STAFF', 'WALK_IN') and p_consent_channel <> 'STAFF_UI')
       or (p_source = 'AI_TEXT' and p_consent_channel <> 'AI_TEXT')
       or (p_source = 'AI_VOICE' and p_consent_channel <> 'AI_VOICE') then
        raise exception 'consent channel must match booking source';
    end if;

    select * into existing_record from public.idempotency_records
    where organization_id = p_organization_id
      and actor_scope = (select auth.uid())::text
      and operation = 'CREATE_SIMULATED_HOLD'
      and idempotency_key = p_idempotency_key for update;
    if found then
        if existing_record.request_hash <> p_request_hash then
            raise exception 'idempotency key was reused with a different request';
        end if;
        select * into appointment_row from public.appointments
        where organization_id = p_organization_id and id = existing_record.response_appointment_id;
        return query select appointment_row.id, appointment_row.booking_reference,
            appointment_row.status, appointment_row.hold_expires_at;
        return;
    end if;

    select * into session_row from public.appointment_sessions
    where organization_id = p_organization_id and id = p_session_id for update;
    if not found or session_row.assignment_id <> p_assignment_id
       or session_row.status not in ('SCHEDULED', 'OPEN') then
        raise exception 'bookable tenant-scoped session required';
    end if;
    if now_at >= session_row.starts_at - make_interval(mins => session_row.booking_cutoff_minutes) then
        raise exception 'booking cutoff has passed';
    end if;

    select * into assignment_row from public.doctor_assignments
    where organization_id = p_organization_id and id = p_assignment_id and active for share;
    if not found then raise exception 'active tenant-scoped doctor assignment required'; end if;

    select p.display_name, c.display_name, cp.phone_e164, l.name
      into patient_name, contact_name, notification_phone, location_name
    from public.patients p
    join public.contacts c on c.organization_id=p_organization_id
      and c.id=p_booked_by_contact_id and c.status='ACTIVE'
    left join public.contact_phones cp on cp.organization_id=p_organization_id
      and cp.id=p_notification_contact_phone_id and cp.contact_id=c.id and cp.status='ACTIVE'
    join public.locations l on l.organization_id=p_organization_id
      and l.id=assignment_row.location_id and l.active
    where p.organization_id=p_organization_id and p.id=p_patient_id and p.status='ACTIVE';
    if not found then raise exception 'active tenant-scoped patient, contact and location required'; end if;
    if p_notification_contact_phone_id is not null and notification_phone is null then
        raise exception 'notification phone must be active and owned by booking contact';
    end if;

    update public.appointments set status='EXPIRED', hold_expires_at=null
    where organization_id=p_organization_id and session_id=p_session_id
      and status='PAYMENT_PENDING' and hold_expires_at <= now_at;

    if session_row.booking_mode = 'EXACT_TIME' then
        if p_slot_id is null then raise exception 'exact-time session requires a slot'; end if;
        select starts_at, ends_at into quoted_starts_at, quoted_ends_at
        from public.appointment_slots where organization_id=p_organization_id
          and id=p_slot_id and session_id=p_session_id and bookable=true for update;
        if not found then raise exception 'bookable matching slot required'; end if;
    else
        if p_slot_id is not null then raise exception 'token session cannot receive a slot'; end if;
        quoted_starts_at := session_row.starts_at;
        quoted_ends_at := session_row.ends_at;
        select count(*) into occupancy from public.appointments
        where organization_id=p_organization_id and session_id=p_session_id
          and status in ('PAYMENT_PENDING','CONFIRMED','COMPLETED','NO_SHOW');
        if occupancy >= session_row.max_patients then raise exception 'session capacity is full'; end if;
    end if;

    quote_version := md5(concat_ws(':', p_assignment_id, p_session_id,
        coalesce(p_slot_id::text, ''), session_row.generation_version,
        assignment_row.fee_minor, assignment_row.currency));

    insert into public.appointments (
        organization_id,patient_id,booked_by_contact_id,notification_contact_phone_id,
        assignment_id,session_id,slot_id,status,hold_expires_at,source,fee_minor,currency,
        contact_snapshot,quote_snapshot,consent_snapshot
    ) values (
        p_organization_id,p_patient_id,p_booked_by_contact_id,p_notification_contact_phone_id,
        p_assignment_id,p_session_id,p_slot_id,'PAYMENT_PENDING',
        now_at + make_interval(secs => p_hold_seconds),p_source,
        assignment_row.fee_minor,assignment_row.currency,
        jsonb_build_object('patient_name',patient_name,'booker_name',contact_name,
            'notification_phone',notification_phone),
        jsonb_build_object('quote_version',quote_version,'doctor_name',assignment_row.display_name,
            'location_name',location_name,'booking_mode',session_row.booking_mode,
            'starts_at',quoted_starts_at,'ends_at',quoted_ends_at,'timezone',session_row.timezone,
            'fee_minor',assignment_row.fee_minor,'currency',assignment_row.currency,
            'hold_seconds',p_hold_seconds),
        jsonb_build_object('confirmed',true,'confirmed_at',now_at,'language',p_consent_language,
            'channel',p_consent_channel,'source',p_source,'quote_version',quote_version)
    ) returning * into appointment_row;

    insert into public.appointment_contact_permissions
        (organization_id,appointment_id,contact_id,can_view,can_manage,grant_source)
    values (p_organization_id,appointment_row.id,p_booked_by_contact_id,true,true,'BOOKING');
    insert into public.payment_attempts
        (organization_id,appointment_id,reference,amount_minor,currency,status)
    values (p_organization_id,appointment_row.id,appointment_row.booking_reference,
        appointment_row.fee_minor,appointment_row.currency,'SIMULATION_PENDING');
    insert into public.idempotency_records
        (organization_id,actor_scope,operation,idempotency_key,request_hash,response_appointment_id)
    values (p_organization_id,(select auth.uid())::text,'CREATE_SIMULATED_HOLD',
        p_idempotency_key,p_request_hash,appointment_row.id);
    return query select appointment_row.id,appointment_row.booking_reference,
        appointment_row.status,appointment_row.hold_expires_at;
end;
$$;

revoke all on function public.create_simulated_appointment_hold(
    uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,boolean,text,text,integer
) from public;
grant execute on function public.create_simulated_appointment_hold(
    uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,boolean,text,text,integer
) to authenticated;

-- Remove the old entry point so explicit consent cannot be bypassed.
drop function public.create_simulated_appointment_hold(
    uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,integer
);

commit;

select jsonb_build_object('phase_2_quote_consent_snapshots',jsonb_build_object(
    'consent_aware_hold_present',to_regprocedure(
      'public.create_simulated_appointment_hold(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,boolean,text,text,integer)') is not null,
    'legacy_hold_removed',to_regprocedure(
      'public.create_simulated_appointment_hold(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,integer)') is null
)) as verification;
