from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def generate_sessions(session: AsyncSession, organization_id: str, through: date) -> int:
    """Idempotently materialize dated sessions from active weekly rules."""
    rules = await session.execute(
        text("""
        select r.*, o.timezone, a.doctor_id
        from public.schedule_rules r
        join public.organizations o on o.id=r.organization_id
        join public.doctor_assignments a on a.organization_id=r.organization_id and a.id=r.assignment_id
        where r.organization_id=:org and r.active and a.active and r.effective_from <= :through
          and (r.effective_until is null or r.effective_until >= current_date)
    """),
        {"org": organization_id, "through": through},
    )
    exceptions = await session.execute(
        text("""
        select assignment_id, local_date, exception_type, local_starts_at, local_ends_at
        from public.schedule_exceptions
        where organization_id=:org and active
          and local_date between current_date and :through
    """),
        {"org": organization_id, "through": through},
    )
    exceptions_by_date = {
        (row["assignment_id"], row["local_date"]): row for row in exceptions.mappings()
    }
    created = 0
    for rule in rules.mappings():
        current = max(date.today(), rule["effective_from"])
        end = min(through, rule["effective_until"] or through)
        zone = ZoneInfo(rule["timezone"])
        while current <= end:
            if current.weekday() == (rule["weekday"] - 1) % 7:
                exception = exceptions_by_date.get((rule["assignment_id"], current))
                if exception and exception["exception_type"] == "CLOSED":
                    current += timedelta(days=1)
                    continue
                local_starts_at = (
                    exception["local_starts_at"]
                    if exception and exception["exception_type"] == "REPLACEMENT_HOURS"
                    else rule["local_starts_at"]
                )
                local_ends_at = (
                    exception["local_ends_at"]
                    if exception and exception["exception_type"] == "REPLACEMENT_HOURS"
                    else rule["local_ends_at"]
                )
                starts = datetime.combine(current, local_starts_at, zone)
                ends = datetime.combine(current, local_ends_at, zone)
                result = await session.execute(
                    text("""
                    insert into public.appointment_sessions
                    (organization_id, assignment_id, doctor_id, starts_at, ends_at, timezone, booking_mode, slot_minutes, max_patients, booking_cutoff_minutes)
                    select :org,:assignment,:doctor,:starts,:ends,:timezone,:mode,:slot_minutes,:max_patients,:cutoff
                    where not exists (
                        select 1 from public.appointment_sessions ex
                        where ex.doctor_id = :doctor
                          and ex.status <> 'CANCELLED'
                          and not (ex.assignment_id = :assignment and ex.starts_at = :starts)
                          and tstzrange(ex.starts_at, ex.ends_at, '[)') && tstzrange(:starts, :ends, '[)')
                    )
                    on conflict (organization_id, assignment_id, starts_at) do update
                    set ends_at = excluded.ends_at,
                        timezone = excluded.timezone,
                        booking_mode = excluded.booking_mode,
                        slot_minutes = excluded.slot_minutes,
                        max_patients = excluded.max_patients,
                        booking_cutoff_minutes = excluded.booking_cutoff_minutes,
                        status = 'SCHEDULED',
                        generation_version = appointment_sessions.generation_version + 1,
                        updated_at = now()
                    where appointment_sessions.status = 'CANCELLED'
                      and not exists (
                          select 1 from public.appointments a
                          where a.organization_id = appointment_sessions.organization_id
                            and a.session_id = appointment_sessions.id
                            and a.status in ('CONFIRMED', 'PAYMENT_PENDING')
                      )
                    returning id
                """),
                    {
                        "org": organization_id,
                        "assignment": rule["assignment_id"],
                        "doctor": rule["doctor_id"],
                        "starts": starts,
                        "ends": ends,
                        "timezone": rule["timezone"],
                        "mode": rule["booking_mode"],
                        "slot_minutes": rule["slot_minutes"],
                        "max_patients": rule["max_patients"],
                        "cutoff": rule["booking_cutoff_minutes"],
                    },
                )
                session_id = result.scalar_one_or_none()
                if session_id and rule["booking_mode"] == "EXACT_TIME":
                    moment = starts
                    while moment + timedelta(minutes=rule["slot_minutes"]) <= ends:
                        await session.execute(
                            text("""
                            insert into public.appointment_slots (organization_id, session_id, assignment_id, starts_at, ends_at)
                            values (:org,:session,:assignment,:starts,:ends)
                            on conflict (organization_id, session_id, starts_at) do nothing
                        """),
                            {
                                "org": organization_id,
                                "session": session_id,
                                "assignment": rule["assignment_id"],
                                "starts": moment,
                                "ends": moment + timedelta(minutes=rule["slot_minutes"]),
                            },
                        )
                        moment += timedelta(minutes=rule["slot_minutes"])
                created += int(session_id is not None)
            current += timedelta(days=1)
    return created


async def generate_active_organization_sessions(session: AsyncSession, through: date) -> int:
    """Keep every active organization's materialized schedule inside one rolling horizon."""
    organizations = await session.execute(
        text("select id from public.organizations where status = 'ACTIVE'")
    )
    created = 0
    for organization_id in organizations.scalars():
        created += await generate_sessions(session, str(organization_id), through)
    return created


async def rebuild_assignment_sessions(
    session: AsyncSession,
    organization_id: str,
    assignment_id: str,
    through: date,
) -> int:
    """Rebuild future unbooked availability while preserving every booked session."""
    params = {"org": organization_id, "assignment": assignment_id}
    await session.execute(
        text("""
            delete from public.appointment_slots sl
            using public.appointment_sessions s
            where sl.organization_id=:org
              and sl.session_id=s.id
              and s.organization_id=:org
              and s.assignment_id=cast(:assignment as uuid)
              and s.starts_at >= now()
              and not exists (
                  select 1 from public.appointments a
                  where a.organization_id=s.organization_id and a.session_id=s.id
              )
        """),
        params,
    )
    await session.execute(
        text("""
            delete from public.appointment_sessions s
            where s.organization_id=:org
              and s.assignment_id=cast(:assignment as uuid)
              and s.starts_at >= now()
              and not exists (
                  select 1 from public.appointments a
                  where a.organization_id=s.organization_id and a.session_id=s.id
              )
        """),
        params,
    )
    await session.execute(
        text("""
            update public.appointment_sessions s
            set status='CANCELLED'
            where s.organization_id=:org
              and s.assignment_id=cast(:assignment as uuid)
              and s.starts_at >= now()
              and s.status <> 'CANCELLED'
              and not exists (
                  select 1 from public.appointments a
                  where a.organization_id=s.organization_id and a.session_id=s.id
                    and a.status in ('CONFIRMED', 'PAYMENT_PENDING')
              )
        """),
        params,
    )
    await session.execute(
        text("""
            delete from public.appointment_slots sl
            using public.appointment_sessions s
            where sl.organization_id=:org
              and sl.session_id=s.id
              and s.organization_id=:org
              and s.assignment_id=cast(:assignment as uuid)
              and s.starts_at >= now()
              and s.status = 'CANCELLED'
              and not exists (
                  select 1 from public.appointments a
                  where a.organization_id=s.organization_id and a.slot_id=sl.id
                    and a.status in ('CONFIRMED', 'PAYMENT_PENDING')
              )
        """),
        params,
    )
    return await generate_sessions(session, organization_id, through)
