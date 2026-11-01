-- Phase 2 corrective migration: make table-column resolution explicit in functions
-- whose RETURNS TABLE fields overlap names such as status.
-- Apply after 20260911000600_phase2_rescheduling.sql.

begin;

do $migration$
declare
    target_oid oid;
    function_definition text;
    updated_definition text;
begin
    foreach target_oid in array array[
        'public.create_simulated_appointment_hold(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,integer)'::regprocedure::oid,
        'public.confirm_simulated_appointment(uuid,uuid)'::regprocedure::oid,
        'public.cancel_appointment(uuid,uuid,integer,text)'::regprocedure::oid
    ]
    loop
        select pg_get_functiondef(target_oid) into function_definition;
        if position('#variable_conflict use_column' in function_definition) = 0 then
            updated_definition := replace(
                function_definition,
                E'AS $function$\r\n',
                E'AS $function$\r\n#variable_conflict use_column\r\n'
            );
            if updated_definition = function_definition then
                updated_definition := replace(
                    function_definition,
                    E'AS $function$\n',
                    E'AS $function$\n#variable_conflict use_column\n'
                );
            end if;
            if updated_definition = function_definition then
                raise exception 'could not patch function %', target_oid::regprocedure;
            end if;
            execute updated_definition;
        end if;
    end loop;
end;
$migration$;

commit;

select jsonb_build_object(
    'phase_2_function_variable_resolution',
    jsonb_build_object(
        'hold_fixed', position('#variable_conflict use_column' in (
            select prosrc from pg_proc where oid =
                'public.create_simulated_appointment_hold(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,integer)'::regprocedure
        )) > 0,
        'confirmation_fixed', position('#variable_conflict use_column' in (
            select prosrc from pg_proc where oid =
                'public.confirm_simulated_appointment(uuid,uuid)'::regprocedure
        )) > 0,
        'cancellation_fixed', position('#variable_conflict use_column' in (
            select prosrc from pg_proc where oid =
                'public.cancel_appointment(uuid,uuid,integer,text)'::regprocedure
        )) > 0
    )
) as phase_2_function_variable_resolution;
