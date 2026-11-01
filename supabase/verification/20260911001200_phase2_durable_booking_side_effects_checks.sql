select jsonb_build_object(
    'phase_2_durable_booking_side_effects', jsonb_build_object(
        'inbox_table_present', to_regclass('public.inbox_events') is not null,
        'outbox_claim_present', to_regprocedure(
            'public.claim_outbox_jobs(integer,integer)'
        ) is not null,
        'outbox_complete_present', to_regprocedure(
            'public.complete_outbox_job(uuid,uuid)'
        ) is not null,
        'outbox_fail_present', to_regprocedure(
            'public.fail_outbox_job(uuid,uuid,text,integer)'
        ) is not null,
        'appointment_side_effect_trigger_present', exists (
            select 1
            from pg_trigger
            where tgrelid = 'public.appointments'::regclass
              and tgname = 'appointments_lifecycle_side_effects'
              and not tgisinternal
        )
    )
) as verification;
