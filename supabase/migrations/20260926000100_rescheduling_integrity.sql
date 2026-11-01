-- Strengthen the existing forward-only reschedule workflow without rewriting applied history.
begin;

create or replace function public.enforce_rescheduled_appointment_integrity()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    prior public.appointments%rowtype;
    target public.appointment_sessions%rowtype;
    assignment public.doctor_assignments%rowtype;
    location_name text;
begin
    if new.supersedes_appointment_id is null then return new; end if;

    select * into prior from public.appointments
    where organization_id=new.organization_id and id=new.supersedes_appointment_id;
    if not found or prior.status <> 'CONFIRMED' then
        raise exception 'a reschedule must supersede one confirmed appointment';
    end if;
    select * into target from public.appointment_sessions
    where organization_id=new.organization_id and id=new.session_id;
    if not found or target.status not in ('SCHEDULED','OPEN')
       or now() >= target.starts_at - make_interval(mins => target.booking_cutoff_minutes) then
        raise exception 'replacement session is not bookable';
    end if;
    select * into assignment from public.doctor_assignments
    where organization_id=new.organization_id and id=target.assignment_id and active;
    if not found then raise exception 'replacement doctor assignment is inactive'; end if;
    select name into location_name from public.locations
    where organization_id=new.organization_id and id=assignment.location_id and active;
    if not found then raise exception 'replacement location is inactive'; end if;
    if prior.fee_minor <> assignment.fee_minor or prior.currency <> assignment.currency then
        raise exception 'fee or currency change requires a new staff-reviewed booking';
    end if;

    new.assignment_id := target.assignment_id;
    new.fee_minor := assignment.fee_minor;
    new.currency := assignment.currency;
    new.quote_snapshot := jsonb_build_object(
        'quote_version', md5(concat_ws(':', target.assignment_id, target.id,
            coalesce(new.slot_id::text,''), target.generation_version, assignment.fee_minor, assignment.currency)),
        'doctor_name', assignment.display_name, 'location_name', location_name,
        'booking_mode', target.booking_mode, 'starts_at', target.starts_at,
        'ends_at', target.ends_at, 'timezone', target.timezone,
        'fee_minor', assignment.fee_minor, 'currency', assignment.currency,
        'rescheduled_from_reference', prior.booking_reference
    );
    new.consent_snapshot := coalesce(prior.consent_snapshot, '{}'::jsonb) || jsonb_build_object(
        'rescheduled_at', now(), 'rescheduled_from_reference', prior.booking_reference
    );

    return new;
end;
$$;

create or replace function public.copy_rescheduled_payment_attempt()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare previous_payment public.payment_attempts%rowtype;
begin
    if new.supersedes_appointment_id is null then return new; end if;
    select * into previous_payment from public.payment_attempts
    where organization_id=new.organization_id and appointment_id=new.supersedes_appointment_id
    order by created_at desc limit 1;
    if found then
        insert into public.payment_attempts
            (organization_id,appointment_id,provider,mode,payment_method,reference,amount_minor,currency,status)
        values (new.organization_id,new.id,previous_payment.provider,previous_payment.mode,
            previous_payment.payment_method,new.booking_reference,new.fee_minor,new.currency,previous_payment.status);
    end if;
    return new;
end;
$$;

drop trigger if exists appointments_enforce_reschedule_integrity on public.appointments;
create trigger appointments_enforce_reschedule_integrity
before insert on public.appointments
for each row execute function public.enforce_rescheduled_appointment_integrity();

drop trigger if exists appointments_copy_rescheduled_payment_attempt on public.appointments;
create trigger appointments_copy_rescheduled_payment_attempt
after insert on public.appointments
for each row execute function public.copy_rescheduled_payment_attempt();

revoke all on function public.enforce_rescheduled_appointment_integrity() from public;
revoke all on function public.copy_rescheduled_payment_attempt() from public;
commit;
