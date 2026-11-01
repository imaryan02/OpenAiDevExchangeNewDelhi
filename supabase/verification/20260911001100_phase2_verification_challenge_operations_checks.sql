select jsonb_build_object(
    'phase_2_verification_challenges', jsonb_build_object(
        'issue_function_present', to_regprocedure(
            'public.issue_verification_challenge(uuid,uuid,integer,text,uuid,integer)'
        ) is not null,
        'verify_function_present', to_regprocedure(
            'public.verify_verification_challenge(uuid,uuid,text,integer)'
        ) is not null,
        'expiry_function_present', to_regprocedure(
            'public.expire_verification_challenges()'
        ) is not null,
        'one_pending_per_phone', exists (
            select 1 from pg_indexes
            where schemaname = 'public'
              and tablename = 'verification_challenges'
              and indexname = 'verification_challenges_one_pending_per_phone_idx'
        )
    )
) as verification;
