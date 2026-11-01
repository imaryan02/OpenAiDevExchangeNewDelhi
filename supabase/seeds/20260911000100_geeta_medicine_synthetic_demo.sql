-- Synthetic demo setup only. Run after Phase 2 migrations.
-- Creates Geeta Medicine, Main Branch, Dr Amit Sharma, exact-time and token schedules.
-- No real patient data is inserted.

do $$
declare v_org_id uuid; v_location_id uuid; v_department_id uuid; v_doctor_id uuid; v_assignment_id uuid;
begin
  select id into v_org_id from public.organizations where name = 'Geeta Medicine' limit 1;
  if v_org_id is null then
    insert into public.organizations (name, organization_type, timezone, status)
    values ('Geeta Medicine', 'CLINIC', 'Asia/Kolkata', 'ACTIVE') returning id into v_org_id;
  end if;
  select id into v_location_id from public.locations where organization_id=v_org_id and name='Main Branch';
  if v_location_id is null then insert into public.locations (organization_id,name,address,timezone) values (v_org_id,'Main Branch','India','Asia/Kolkata') returning id into v_location_id; end if;
  select id into v_department_id from public.departments where organization_id=v_org_id and name='General Medicine';
  if v_department_id is null then insert into public.departments (organization_id,name) values (v_org_id,'General Medicine') returning id into v_department_id; end if;
  select id into v_doctor_id from public.doctors where canonical_name='Dr Amit Sharma' limit 1;
  if v_doctor_id is null then insert into public.doctors (canonical_name,qualifications) values ('Dr Amit Sharma',array['MBBS']) returning id into v_doctor_id; end if;
  select id into v_assignment_id from public.doctor_assignments where organization_id=v_org_id and doctor_id=v_doctor_id and location_id=v_location_id and department_id=v_department_id;
  if v_assignment_id is null then insert into public.doctor_assignments (organization_id,doctor_id,location_id,department_id,display_name,fee_minor,currency) values (v_org_id,v_doctor_id,v_location_id,v_department_id,'Dr Amit Sharma',50000,'INR') returning id into v_assignment_id; end if;
  if not exists (select 1 from public.schedule_rules where organization_id=v_org_id and assignment_id=v_assignment_id and weekday=1 and booking_mode='SESSION_TOKEN') then
    insert into public.schedule_rules (organization_id,assignment_id,weekday,local_starts_at,local_ends_at,booking_mode,max_patients,effective_from) values (v_org_id,v_assignment_id,1,'10:00','12:00','SESSION_TOKEN',6,current_date);
  end if;
  if not exists (select 1 from public.schedule_rules where organization_id=v_org_id and assignment_id=v_assignment_id and weekday=5 and booking_mode='SESSION_TOKEN') then
    insert into public.schedule_rules (organization_id,assignment_id,weekday,local_starts_at,local_ends_at,booking_mode,max_patients,effective_from) values (v_org_id,v_assignment_id,5,'16:00','18:00','SESSION_TOKEN',30,current_date);
  end if;
end $$;

select jsonb_build_object('organization','Geeta Medicine','synthetic_only',true,'timezone',(select timezone from public.organizations where name='Geeta Medicine' limit 1),'token_capacity',(select max_patients from public.schedule_rules r join public.organizations o on o.id=r.organization_id where o.name='Geeta Medicine' and booking_mode='SESSION_TOKEN' limit 1)) as geeta_demo_seed;
