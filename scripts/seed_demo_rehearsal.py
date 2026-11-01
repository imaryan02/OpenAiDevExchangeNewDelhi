"""
Seed and reset repeatable synthetic demonstration records for the Geeta Medicine conference rehearsal.
Safe to run repeatedly; ensures idempotent setup of clinic, doctors, availability, caller profiles,
and an active test appointment for lookup, cancellation, and rescheduling journeys.
"""

import asyncio
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

# Add backend directory to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.config import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def seed_rehearsal_data() -> None:
    settings = get_settings()
    if not settings.database_url:
        print("[ERROR] DATABASE_URL is not configured in settings or .env.")
        sys.exit(1)

    print("Connecting to database...")
    engine = create_async_engine(settings.database_url)

    async with engine.begin() as conn:
        # 1. Organization
        org_res = await conn.execute(
            text("select id, name, timezone from public.organizations where name = 'Geeta Medicine' limit 1")
        )
        org = org_res.mappings().one_or_none()
        if org is None:
            org_insert = await conn.execute(
                text("""
                    insert into public.organizations (name, organization_type, timezone, status)
                    values ('Geeta Medicine', 'CLINIC', 'Asia/Kolkata', 'ACTIVE')
                    returning id, name, timezone
                """)
            )
            org = org_insert.mappings().one()
            print(f"[+] Created organization: {org['name']} ({org['id']})")
        else:
            print(f"[*] Found organization: {org['name']} ({org['id']})")
        org_id: UUID = org["id"]

        # 2. Location
        loc_res = await conn.execute(
            text("select id, name from public.locations where organization_id = :org and name = 'Main Branch' limit 1"),
            {"org": org_id},
        )
        loc = loc_res.mappings().one_or_none()
        if loc is None:
            loc_insert = await conn.execute(
                text("""
                    insert into public.locations (organization_id, name, address, timezone)
                    values (:org, 'Main Branch', 'Sector 14, Gurugram, Haryana', 'Asia/Kolkata')
                    returning id, name
                """),
                {"org": org_id},
            )
            loc = loc_insert.mappings().one()
            print(f"[+] Created location: {loc['name']} ({loc['id']})")
        else:
            print(f"[*] Found location: {loc['name']} ({loc['id']})")
        loc_id: UUID = loc["id"]

        # 3. Departments
        departments = ["General Medicine", "Gynaecology", "Pediatrics"]
        dept_ids: dict[str, UUID] = {}
        for dname in departments:
            d_res = await conn.execute(
                text("select id from public.departments where organization_id = :org and name = :name"),
                {"org": org_id, "name": dname},
            )
            d_row = d_res.mappings().one_or_none()
            if d_row is None:
                d_ins = await conn.execute(
                    text("insert into public.departments (organization_id, name, active) values (:org, :name, true) returning id"),
                    {"org": org_id, "name": dname},
                )
                dept_ids[dname] = d_ins.mappings().one()["id"]
                print(f"[+] Created department: {dname}")
            else:
                dept_ids[dname] = d_row["id"]

        # 4. Doctors and Assignments
        doctors_spec = [
            {
                "canonical_name": "Dr Amit Kumar",
                "display_name": "Dr Amit Kumar",
                "dept": "General Medicine",
                "qualifications": ["MBBS", "MD (Internal Medicine)"],
                "fee_minor": 50000,  # Rs 500
            },
            {
                "canonical_name": "Dr Sweta Gupta",
                "display_name": "Dr Sweta Gupta",
                "dept": "Gynaecology",
                "qualifications": ["MBBS", "MS (OB-GYN)"],
                "fee_minor": 70000,  # Rs 700
            },
        ]

        assignment_ids: dict[str, UUID] = {}
        for dspec in doctors_spec:
            doc_res = await conn.execute(
                text("select id from public.doctors where canonical_name = :name limit 1"),
                {"name": dspec["canonical_name"]},
            )
            doc_row = doc_res.mappings().one_or_none()
            if doc_row is None:
                doc_ins = await conn.execute(
                    text("insert into public.doctors (canonical_name, qualifications) values (:name, :qual) returning id"),
                    {"name": dspec["canonical_name"], "qual": dspec["qualifications"]},
                )
                doc_id = doc_ins.mappings().one()["id"]
            else:
                doc_id = doc_row["id"]

            asgn_res = await conn.execute(
                text("""
                    select id from public.doctor_assignments
                    where organization_id = :org and doctor_id = :doc and location_id = :loc and department_id = :dept
                """),
                {"org": org_id, "doc": doc_id, "loc": loc_id, "dept": dept_ids[dspec["dept"]]},
            )
            asgn_row = asgn_res.mappings().one_or_none()
            if asgn_row is None:
                asgn_ins = await conn.execute(
                    text("""
                        insert into public.doctor_assignments
                          (organization_id, doctor_id, location_id, department_id, display_name, fee_minor, currency, active)
                        values
                          (:org, :doc, :loc, :dept, :name, :fee, 'INR', true)
                        returning id
                    """),
                    {
                        "org": org_id,
                        "doc": doc_id,
                        "loc": loc_id,
                        "dept": dept_ids[dspec["dept"]],
                        "name": dspec["display_name"],
                        "fee": dspec["fee_minor"],
                    },
                )
                assignment_ids[dspec["display_name"]] = asgn_ins.mappings().one()["id"]
                print(f"[+] Created doctor assignment: {dspec['display_name']}")
            else:
                assignment_ids[dspec["display_name"]] = asgn_row["id"]
                print(f"[*] Found doctor assignment: {dspec['display_name']}")

        # 5. Materialize Active Token Sessions for Today & Tomorrow (IST)
        tz = ZoneInfo("Asia/Kolkata")
        today_local = datetime.now(tz).date()

        for d_offset in range(3):
            target_date = today_local + timedelta(days=d_offset)
            # Dr Amit: 10:00 to 12:00 IST
            amit_start = datetime.combine(target_date, time(10, 0), tz)
            amit_end = datetime.combine(target_date, time(12, 0), tz)

            # Dr Sweta: 16:00 to 18:00 IST
            sweta_start = datetime.combine(target_date, time(16, 0), tz)
            sweta_end = datetime.combine(target_date, time(18, 0), tz)

            for asgn_name, s_start, s_end in [
                ("Dr Amit Kumar", amit_start, amit_end),
                ("Dr Sweta Gupta", sweta_start, sweta_end),
            ]:
                asgn_id = assignment_ids[asgn_name]
                # Insert or revive session if not already scheduled
                await conn.execute(
                    text("""
                        insert into public.appointment_sessions
                          (organization_id, assignment_id, doctor_id, starts_at, ends_at, timezone,
                           booking_mode, max_patients, booking_cutoff_minutes, status)
                        select
                          :org, :asgn, (select doctor_id from public.doctor_assignments where id = :asgn),
                          :starts, :ends, 'Asia/Kolkata', 'SESSION_TOKEN', 20, 15, 'SCHEDULED'
                        where not exists (
                          select 1 from public.appointment_sessions ex
                          where ex.doctor_id = (select doctor_id from public.doctor_assignments where id = :asgn)
                            and ex.status <> 'CANCELLED'
                            and tstzrange(ex.starts_at, ex.ends_at, '[)') && tstzrange(:starts, :ends, '[)')
                        )
                        on conflict (organization_id, assignment_id, starts_at) do update
                        set ends_at = excluded.ends_at,
                            status = 'SCHEDULED'
                        where appointment_sessions.status = 'CANCELLED'
                    """),
                    {
                        "org": org_id,
                        "asgn": asgn_id,
                        "starts": s_start,
                        "ends": s_end,
                    },
                )
        print("[+] Ensured bookable appointment sessions for the next 3 days.")

        # 6. Caller Contact & Synthetic Family
        # This is the inbound caller's mobile number. The VoiceLink DID is
        # +919429397279 and must never be used as the caller identity.
        demo_phone = "+918529586946"
        await conn.execute(
            text(
                "update public.contact_phones set status='DISABLED', version=version+1 "
                "where organization_id=:org and phone_e164='+919429397279' "
                "and status='ACTIVE'"
            ),
            {"org": org_id},
        )
        contact_res = await conn.execute(
            text("""
                select c.id as contact_id, cp.id as phone_id
                from public.contacts c
                join public.contact_phones cp on cp.contact_id = c.id
                where c.organization_id = :org and cp.phone_e164 = :phone and cp.status = 'ACTIVE'
            """),
            {"org": org_id, "phone": demo_phone},
        )
        contact_row = contact_res.mappings().one_or_none()
        if contact_row is None:
            c_ins = await conn.execute(
                text("insert into public.contacts (organization_id, display_name, name_source) values (:org, 'Aryan Gupta', 'STATED') returning id"),
                {"org": org_id},
            )
            contact_id = c_ins.mappings().one()["id"]
            p_ins = await conn.execute(
                text("insert into public.contact_phones (organization_id, contact_id, phone_e164, status) values (:org, :c, :p, 'ACTIVE') returning id"),
                {"org": org_id, "c": contact_id, "p": demo_phone},
            )
            phone_id = p_ins.mappings().one()["id"]
            print(f"[+] Created contact Aryan Gupta ({demo_phone})")
        else:
            contact_id = contact_row["contact_id"]
            phone_id = contact_row["phone_id"]
            print(f"[*] Found contact Aryan Gupta ({demo_phone})")

        # Patients linked to the authenticated rehearsal caller.
        patient_records = [
            ("Aryan Gupta", "SELF"),
            ("Bibha Gupta", "MOTHER"),
            ("Ramesh Gupta", "FATHER"),
        ]
        patient_ids: dict[str, UUID] = {}
        for pname, rel in patient_records:
            pat_res = await conn.execute(
                text("""
                    select p.id from public.patients p
                    join public.patient_contacts pc on pc.patient_id = p.id
                    where p.organization_id = :org and pc.contact_id = :c and lower(p.display_name) = lower(:name)
                """),
                {"org": org_id, "c": contact_id, "name": pname},
            )
            pat_row = pat_res.mappings().one_or_none()
            if pat_row is None:
                pat_ins = await conn.execute(
                    text("insert into public.patients (organization_id, display_name) values (:org, :name) returning id"),
                    {"org": org_id, "name": pname},
                )
                pid = pat_ins.mappings().one()["id"]
                await conn.execute(
                    text("""
                        insert into public.patient_contacts (organization_id, contact_id, patient_id, relationship, relationship_status)
                        values (:org, :c, :p, :r, 'RECORDED')
                    """),
                    {"org": org_id, "c": contact_id, "p": pid, "r": rel},
                )
                patient_ids[pname] = pid
                print(f"[+] Linked patient: {pname} ({rel})")
            else:
                patient_ids[pname] = pat_row["id"]
                print(f"[*] Found patient: {pname} ({rel})")

        # 7. Seed One Active Confirmed Appointment for Rehearsal Lookup/Change
        # Book Bibha with Dr Sweta for tomorrow
        target_session_res = await conn.execute(
            text("""
                select id from public.appointment_sessions
                where organization_id = :org and assignment_id = :asgn and starts_at > now()
                order by starts_at asc limit 1
            """),
            {"org": org_id, "asgn": assignment_ids["Dr Sweta Gupta"]},
        )
        sess_row = target_session_res.mappings().one_or_none()
        if sess_row is not None:
            sess_id = sess_row["id"]
            # Check if active appointment already exists
            existing_app = await conn.execute(
                text("""
                    select booking_reference, status from public.appointments
                    where organization_id = :org and patient_id = :pat and session_id = :sess and status = 'CONFIRMED'
                """),
                {"org": org_id, "pat": patient_ids["Bibha Gupta"], "sess": sess_id},
            )
            app_row = existing_app.mappings().one_or_none()
            if app_row is None:
                ref = f"GM-{uuid4().hex[:10].upper()}"
                app_ins = await conn.execute(
                    text("""
                        insert into public.appointments
                          (organization_id, patient_id, booked_by_contact_id, notification_contact_phone_id,
                           assignment_id, session_id, token_number, queue_status, status, source,
                           fee_minor, currency, booking_reference)
                        values
                          (:org, :pat, :c, :phone_id, :asgn, :sess, 1, 'NOT_ARRIVED', 'CONFIRMED', 'AI_VOICE',
                           70000, 'INR', :ref)
                        returning id, booking_reference
                    """),
                    {
                        "org": org_id,
                        "pat": patient_ids["Bibha Gupta"],
                        "c": contact_id,
                        "phone_id": phone_id,
                        "asgn": assignment_ids["Dr Sweta Gupta"],
                        "sess": sess_id,
                        "ref": ref,
                    },
                )
                app_data = app_ins.mappings().one()
                # Grant management permissions to Aryan's contact
                await conn.execute(
                    text("""
                        insert into public.appointment_contact_permissions
                          (organization_id, appointment_id, contact_id, can_view, can_manage, grant_source)
                        values
                          (:org, :aid, :cid, true, true, 'AUTHORIZED_WORKFLOW')
                    """),
                    {"org": org_id, "aid": app_data["id"], "cid": contact_id},
                )
                print(f"[+] Created rehearsal appointment: {app_data['booking_reference']} (Bibha Gupta / Dr Sweta Gupta)")
            else:
                print(f"[*] Rehearsal appointment already active: {app_row['booking_reference']}")

    await engine.dispose()
    print("\n" + "=" * 65)
    print("CONFERENCE REHEARSAL FIXTURES READY")
    print("=" * 65)
    print("Clinic:            Geeta Medicine (Asia/Kolkata)")
    print(f"Caller Phone:      {demo_phone}")
    print("Known Caller:      Aryan Gupta")
    print("Saved Family:      Bibha Gupta (Mother), Ramesh Gupta (Father)")
    print("Doctors:           Dr Amit Kumar (General Medicine - Rs 500)")
    print("                   Dr Sweta Gupta (Gynaecology - Rs 700)")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(seed_rehearsal_data())
