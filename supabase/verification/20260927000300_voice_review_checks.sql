-- Read-only checks after applying 20260927000300_voice_review_observability.sql.
select
  to_regclass('public.voice_observability_messages') is not null as messages_table_exists,
  to_regclass('public.voice_observability_content_access') is not null as access_audit_table_exists,
  to_regclass('public.voice_observability_attempts') is not null as attempts_table_exists,
  to_regclass('public.voice_messages_call_sequence_idx') is not null as messages_call_index_exists,
  to_regclass('public.voice_messages_expiry_idx') is not null as messages_expiry_index_exists,
  to_regclass('public.voice_attempts_org_time_idx') is not null as attempts_time_index_exists,
  (select count(*) = 3 from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relrowsecurity and c.relname in
      ('voice_observability_messages', 'voice_observability_content_access',
       'voice_observability_attempts')) as review_tables_rls_enabled,
  not exists (select 1 from information_schema.role_table_grants
    where table_schema = 'public' and table_name = 'voice_observability_messages'
      and grantee in ('anon', 'authenticated')) as text_direct_access_revoked;

-- Run after a new authorized call; no conversation content or provider identifiers are returned.
select c.id, c.engine, c.status, c.duration_ms, c.events_complete,
       c.capture_policy ->> 'transcripts' as transcript_capture,
       (select count(*) from public.voice_observability_messages m
         where m.organization_id = c.organization_id and m.call_id = c.id
           and m.expires_at > now()) as retained_messages,
       (select count(*) from public.voice_observability_content_access a
         where a.organization_id = c.organization_id and a.call_id = c.id) as audited_reads
  from public.voice_observability_calls c order by c.started_at desc limit 10;
