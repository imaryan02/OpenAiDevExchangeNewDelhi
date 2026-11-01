-- Phase: 2.3b — Atomic staff rescheduling
-- Apply after 20260911000500_phase2_cancellation_outbox.sql.

begin;

create or replace function public.reschedule_appointment(
    p_organization_id uuid,
    p_appointment_id uuid,
    p_expected_version integer,
    p_new_session_id uuid,
    p_new_slot_id uuid
)
returns table (old_appointment_id uuid, replacement_appointment_id uuid, replacement_reference text, replacement_token integer)
language plpgsql security definer set search_path = '' as $$
declare old_row public.appointments%rowtype; new_row public.appointments%rowtype;
declare target_session public.appointment_sessions%rowtype; occupancy integer; new_token integer;
begin
    if not (select private.is_org_booking_staff(p_organization_id)) then raise exception 'booking staff authorization required'; end if;
    select * into old_row from public.appointments where organization_id=p_organization_id and id=p_appointment_id for update;
    if not found or old_row.status <> 'CONFIRMED' or old_row.version <> p_expected_version then raise exception 'appointment is not eligible for rescheduling'; end if;
    if old_row.session_id = p_new_session_id and old_row.slot_id is not distinct from p_new_slot_id then raise exception 'replacement must differ from original appointment'; end if;
    perform 1 from public.appointment_sessions where organization_id=p_organization_id and id in (old_row.session_id, p_new_session_id) order by id for update;
    select * into target_session from public.appointment_sessions where organization_id=p_organization_id and id=p_new_session_id;
    if not found or target_session.status not in ('SCHEDULED','OPEN') then raise exception 'new session is unavailable'; end if;
    if target_session.assignment_id = old_row.assignment_id then
        null;
    end if;
    if target_session.booking_mode='EXACT_TIME' then
        if p_new_slot_id is null then raise exception 'exact-time session requires a slot'; end if;
        perform 1 from public.appointment_slots where organization_id=p_organization_id and id=p_new_slot_id and session_id=p_new_session_id and bookable for update;
        if not found then raise exception 'new slot is unavailable'; end if;
    else
        if p_new_slot_id is not null then raise exception 'token session cannot use an exact slot'; end if;
        select count(*) into occupancy from public.appointments where organization_id=p_organization_id and session_id=p_new_session_id and status in ('PAYMENT_PENDING','CONFIRMED','COMPLETED','NO_SHOW');
        if occupancy >= target_session.max_patients then raise exception 'new session is full'; end if;
        update public.appointment_sessions set next_token=next_token+1 where organization_id=p_organization_id and id=p_new_session_id returning next_token into new_token;
    end if;
    if old_row.fee_minor <> (select fee_minor from public.doctor_assignments where organization_id=p_organization_id and id=target_session.assignment_id) then raise exception 'fee change requires staff review'; end if;
    insert into public.appointments (organization_id,patient_id,booked_by_contact_id,notification_contact_phone_id,assignment_id,session_id,slot_id,token_number,queue_status,status,source,fee_minor,currency,contact_snapshot,quote_snapshot,consent_snapshot,supersedes_appointment_id)
    values (p_organization_id,old_row.patient_id,old_row.booked_by_contact_id,old_row.notification_contact_phone_id,target_session.assignment_id,p_new_session_id,p_new_slot_id,new_token,'NOT_ARRIVED','CONFIRMED',old_row.source,old_row.fee_minor,old_row.currency,old_row.contact_snapshot,old_row.quote_snapshot,old_row.consent_snapshot,old_row.id)
    returning * into new_row;
    insert into public.appointment_contact_permissions (organization_id,appointment_id,contact_id,can_view,can_manage,grant_source)
    select organization_id,new_row.id,contact_id,can_view,can_manage,'AUTHORIZED_WORKFLOW' from public.appointment_contact_permissions where organization_id=p_organization_id and appointment_id=old_row.id and revoked_at is null;
    update public.appointments set status='RESCHEDULED', queue_status=null, version=version+1 where organization_id=p_organization_id and id=old_row.id;
    insert into public.outbox_jobs (organization_id,job_type,aggregate_id,dedupe_key,payload) values (p_organization_id,'APPOINTMENT_RESCHEDULED',new_row.id,'appointment-rescheduled:'||new_row.id::text,jsonb_build_object('old_appointment_id',old_row.id,'replacement_appointment_id',new_row.id));
    return query select old_row.id,new_row.id,new_row.booking_reference,new_row.token_number;
end; $$;

revoke all on function public.reschedule_appointment(uuid,uuid,integer,uuid,uuid) from public;
grant execute on function public.reschedule_appointment(uuid,uuid,integer,uuid,uuid) to authenticated;
commit;
