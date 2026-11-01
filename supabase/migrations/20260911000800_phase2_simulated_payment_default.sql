-- Phase 2 corrective migration: holds use the local payment simulator by default.
-- Apply after 20260911000700_phase2_function_variable_resolution.sql.

begin;

alter table public.payment_attempts
    alter column mode set default 'SIMULATED';

commit;

select jsonb_build_object(
    'phase_2_simulated_payment_default',
    jsonb_build_object(
        'mode_default', (
            select column_default
            from information_schema.columns
            where table_schema = 'public'
              and table_name = 'payment_attempts'
              and column_name = 'mode'
        ),
        'configured', coalesce((
            select column_default like '%SIMULATED%'
            from information_schema.columns
            where table_schema = 'public'
              and table_name = 'payment_attempts'
              and column_name = 'mode'
        ), false)
    )
) as phase_2_simulated_payment_default;
