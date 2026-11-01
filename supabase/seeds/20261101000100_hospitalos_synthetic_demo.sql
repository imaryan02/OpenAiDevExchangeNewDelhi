-- Synthetic HospitalOS demo only. Run only against the intended demo database.
-- Geeta Medicine is linked to its existing Main Branch; all resource numbers are invented.
begin;

do $$
declare
    geeta_org uuid;
    geeta_location uuid;
begin
    select o.id, l.id into geeta_org, geeta_location
    from public.organizations o
    join public.locations l on l.organization_id=o.id
    where o.name='Geeta Medicine' and o.status='ACTIVE'
      and l.name='Main Branch' and l.active
    order by o.id
    limit 1;
    if geeta_org is null then
        raise exception 'Active Geeta Medicine / Main Branch not found';
    end if;

    insert into public.hospitalos_facilities
        (slug,organization_id,location_id,name,area,address,latitude,longitude,
         cost_category,emergency_open,ed_bays_ready,icu_beds_ready,ventilators_ready,
         ct_available,trauma_available,pediatric_available,obstetric_available,receiving_enabled)
    values
        ('geeta-medicine',geeta_org,geeta_location,'Geeta Medicine','Central Delhi demo area',
         'Synthetic location for demonstration',28.633000,77.219000,
         'CHARITABLE',true,2,1,1,true,true,false,false,true)
    on conflict (slug) do update
       set organization_id=excluded.organization_id,
           location_id=excluded.location_id,
           receiving_enabled=true;

    insert into public.hospitalos_facilities
        (slug,name,area,address,latitude,longitude,cost_category,emergency_open,
         ed_bays_ready,icu_beds_ready,ventilators_ready,ct_available,trauma_available,
         pediatric_available,obstetric_available,receiving_enabled)
    values
        ('north-demo-hospital','North Demo Hospital','North Delhi demo area',
         'Synthetic location for demonstration',28.686000,77.205000,'GOVERNMENT',true,
         3,0,0,false,true,true,false,false),
        ('east-demo-medical-centre','East Demo Medical Centre','East Delhi demo area',
         'Synthetic location for demonstration',28.630000,77.290000,'PRIVATE',true,
         1,2,1,true,false,false,true,false)
    on conflict (slug) do update
       set verified_at=now(), updated_at=now();
end;
$$;

commit;
