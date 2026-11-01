-- Phase 2 payment-method capture for manual and AI-assisted bookings.
-- Existing prototype payment processing remains simulated.

begin;

alter table public.payment_attempts
    add column if not exists payment_method text;

update public.payment_attempts
set payment_method = case
    when mode = 'PAY_AT_CLINIC' then 'CASH'
    else 'ONLINE'
end
where payment_method is null;

alter table public.payment_attempts
    alter column payment_method set default 'ONLINE',
    alter column payment_method set not null;

alter table public.payment_attempts
    drop constraint if exists payment_attempts_payment_method_check;

alter table public.payment_attempts
    add constraint payment_attempts_payment_method_check
    check (payment_method in ('CASH', 'UPI', 'CARD', 'ONLINE'));

commit;

select jsonb_build_object(
    'phase_2_payment_methods',
    jsonb_build_object(
        'column_present', exists (
            select 1 from information_schema.columns
            where table_schema='public' and table_name='payment_attempts'
              and column_name='payment_method'
        ),
        'allowed_methods', jsonb_build_array('CASH', 'UPI', 'CARD', 'ONLINE')
    )
) as verification;
