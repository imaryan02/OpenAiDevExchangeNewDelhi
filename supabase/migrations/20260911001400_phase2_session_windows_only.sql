-- Preserve all historical data while preventing creation of new exact-time rules.
alter table public.schedule_rules
    drop constraint if exists schedule_rules_session_windows_only_check;
alter table public.schedule_rules
    add constraint schedule_rules_session_windows_only_check
    check (booking_mode = 'SESSION_TOKEN') not valid;
