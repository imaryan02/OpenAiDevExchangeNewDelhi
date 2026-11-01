select jsonb_build_object('verification',jsonb_build_object(
  'phase_2_quote_consent_snapshots',jsonb_build_object(
    'consent_aware_hold_present',to_regprocedure(
      'public.create_simulated_appointment_hold(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,boolean,text,text,integer)') is not null,
    'legacy_hold_removed',to_regprocedure(
      'public.create_simulated_appointment_hold(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,integer)') is null,
    'snapshot_columns_required',(select count(*)=3 from information_schema.columns
      where table_schema='public' and table_name='appointments'
        and column_name in ('contact_snapshot','quote_snapshot','consent_snapshot')
        and is_nullable='NO')
  )
)) as verification;
