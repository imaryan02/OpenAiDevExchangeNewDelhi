-- Caller history: only trusted carrier numbers, with existing clinic RLS unchanged.
begin;
alter table public.voice_observability_calls
  add column if not exists caller_number text,
  add column if not exists caller_number_source text;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'voice_calls_caller_number_check'
      and conrelid = 'public.voice_observability_calls'::regclass) then
    alter table public.voice_observability_calls add constraint voice_calls_caller_number_check
      check (caller_number is null or caller_number ~ '^\+[1-9][0-9]{7,14}$');
  end if;
  if not exists (select 1 from pg_constraint where conname = 'voice_calls_caller_source_check'
      and conrelid = 'public.voice_observability_calls'::regclass) then
    alter table public.voice_observability_calls add constraint voice_calls_caller_source_check
      check (caller_number_source is null or caller_number_source in ('CARRIER', 'RUNTIME_LINK'));
  end if;
end $$;
create index if not exists voice_calls_org_caller_started_idx
  on public.voice_observability_calls (organization_id, caller_number, started_at desc, id desc)
  where caller_number is not null;

-- Recover only exact tenant/provider-call matches; never infer from a patient or transcript.
update public.voice_observability_calls c
   set caller_number = s.caller_phone_e164, caller_number_source = 'RUNTIME_LINK'
  from public.voice_call_sessions s
 where c.organization_id = s.organization_id and c.provider_call_id = s.provider_call_id
   and c.provider = 'VOICELINK' and c.caller_number is null
   and s.caller_phone_e164 ~ '^\+[1-9][0-9]{7,14}$';
commit;
