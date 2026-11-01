import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.twilio import TwilioWhatsAppClient

TOOLS: list[dict[str, object]] = [
    {
        "type": "function",
        "name": "suggest_department",
        "description": (
            "Administratively route a caller's problem description to an active clinic "
            "department and its doctors. This does not diagnose or assess the caller."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "problem_description": {
                    "type": "string",
                    "description": "The caller's own brief description of their problem.",
                }
            },
            "required": ["problem_description"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_availability",
        "description": (
            "Find bookable sessions in a date range. Use this for availability questions and "
            "omit doctor_name to discover available doctors and departments."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "from_at": {
                    "type": "string",
                    "description": "ISO 8601 datetime with timezone, in Asia/Kolkata when possible.",
                },
                "to_at": {
                    "type": "string",
                    "description": "ISO 8601 datetime with timezone, after from_at.",
                },
                "doctor_name": {
                    "type": ["string", "null"],
                    "description": "Optional doctor name filter.",
                },
                "department_name": {
                    "type": ["string", "null"],
                    "description": "Optional canonical department name filter.",
                },
            },
            "required": ["from_at", "to_at", "doctor_name", "department_name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "lookup_caller_family",
        "description": "For a supplied E.164 mobile number, identify the saved caller and linked family profiles. This does not reveal appointments.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "phone_e164": {
                    "type": "string",
                    "description": "The caller mobile in E.164 format, for example +919812345678.",
                }
            },
            "required": ["phone_e164"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "start_phone_verification",
        "description": "Send a one-time code to a saved caller before private appointment lookup.",
    },
    {
        "type": "function",
        "name": "verify_phone_code",
        "description": "Verify a caller-supplied one-time code.",
    },
    {
        "type": "function",
        "name": "list_upcoming_appointments",
        "description": "List upcoming appointments for the caller's mobile number.",
    },
    {
        "type": "function",
        "name": "prepare_booking_offer",
        "description": "Prepare a signed short-lived offer for a saved patient.",
    },
    {
        "type": "function",
        "name": "confirm_booking_offer",
        "description": "Confirm the active offer after explicit caller consent.",
    },
    {
        "type": "function",
        "name": "get_clinic_information",
        "description": "Get grounded clinic details including name, address, active departments, and doctors.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "cancel_appointment",
        "description": "Cancel an existing upcoming appointment for the caller after explicit confirmation.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "booking_reference": {
                    "type": "string",
                    "description": "The clinic booking reference (e.g. GM-1234567890).",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for cancellation provided by caller.",
                },
            },
            "required": ["booking_reference", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "reschedule_appointment",
        "description": "Move an existing confirmed appointment to a new available session date/time.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "booking_reference": {
                    "type": "string",
                    "description": "The existing clinic booking reference (e.g. GM-1234567890).",
                },
                "new_session_id": {
                    "type": "string",
                    "description": "The UUID of the new available session chosen by the caller.",
                },
                "new_slot_id": {
                    "type": ["string", "null"],
                    "description": "Optional slot ID if the new session uses exact-time booking.",
                },
            },
            "required": ["booking_reference", "new_session_id", "new_slot_id"],
            "additionalProperties": False,
        },
    },
]


URGENT_WARNING_PHRASES = (
    "chest pain",
    "difficulty breathing",
    "trouble breathing",
    "cannot breathe",
    "can't breathe",
    "breathless",
    "shortness of breath",
    "unconscious",
    "not waking",
    "severe bleeding",
    "seizure",
    "convulsion",
    "face drooping",
    "slurred speech",
    "one sided weakness",
    "suicidal",
    "heart attack",
    "सीने में दर्द",
    "सांस लेने में दिक्कत",
    "बेहोश",
    "बहुत खून",
    "saans nahi",
    "seene me dard",
    "seene mein dard",
    "seene me",
    "seene mein",
    "chhati me",
    "chhati mein",
    "dil ka daura",
    "behosh",
    "khoon",
)

GYNAE_ROUTING_PHRASES = (
    "pregnant",
    "pregnancy",
    "period",
    "menstrual",
    "menstruation",
    "vaginal",
    "uterus",
    "ovary",
    "fertility",
    "contraception",
    "gynae",
    "gynecology",
    "gynaecology",
    "गर्भ",
    "पीरियड",
    "माहवारी",
)


def _normalize_doctor_name(value: object) -> str:
    words = re.sub(r"[^\w\s\u0900-\u097f]+", " ", str(value).casefold()).split()
    ignored = {"dr", "doctor", "docter", "डॉ", "डॉक्टर", "ji", "sahab", "saab", "sir", "madam", "जी", "साहब"}
    return " ".join(word for word in words if word not in ignored)


def _match_doctor(requested: object, available: list[str]) -> tuple[str | None, list[str]]:
    target = _normalize_doctor_name(requested)
    if not target:
        return None, []
    scored: list[tuple[float, str]] = []
    target_words = [w for w in target.split() if w]
    for doctor in available:
        candidate = _normalize_doctor_name(doctor)
        candidate_words = [w for w in candidate.split() if w]
        if target == candidate:
            score = 1.0
        elif target_words and set(target_words).issubset(set(candidate_words)):
            score = 0.92
        elif candidate_words and set(candidate_words).issubset(set(target_words)):
            score = 0.88
        else:
            whole = SequenceMatcher(None, target, candidate).ratio()
            word_matches = [
                max((SequenceMatcher(None, tw, cw).ratio() for cw in candidate_words), default=0.0)
                for tw in target_words
            ]
            avg_word_score = sum(word_matches) / len(word_matches) if word_matches else 0.0
            score = max(whole, avg_word_score)
        scored.append((score, doctor))

    matches = [(s, name) for s, name in scored if s >= 0.72]
    if not matches:
        return None, []

    matches.sort(key=lambda x: x[0], reverse=True)
    top_score = matches[0][0]
    top_candidates = [name for s, name in matches if s >= top_score - 0.05 and s >= 0.85]
    if len(top_candidates) > 1:
        return None, top_candidates

    return matches[0][1], []


def _best_doctor_match(requested: object, available: list[str]) -> str | None:
    matched, _ = _match_doctor(requested, available)
    return matched


def _best_department_match(requested: object, available: list[str]) -> str | None:
    target = re.sub(r"[^a-z0-9]+", " ", str(requested).casefold()).strip()
    if any(term in target for term in ("gynae", "gynec", "gynaec", "women", "ladies", "delivery")):
        return next((name for name in available if "gyn" in name.casefold()), None)
    if any(term in target for term in ("general", "physician", "medicine", "fever", "gp", "family doctor")):
        return next((name for name in available if "general" in name.casefold()), None)
    scored = [
        (SequenceMatcher(None, target, name.casefold()).ratio(), name) for name in available
    ]
    score, name = max(scored, default=(0.0, ""))
    return name if score >= 0.72 else None


def _problem_route(problem_description: object) -> str:
    problem = " ".join(str(problem_description).casefold().split())
    if any(phrase in problem for phrase in URGENT_WARNING_PHRASES):
        return "URGENT"
    if any(phrase in problem for phrase in GYNAE_ROUTING_PHRASES):
        return "GYNAE"
    return "GENERAL_MEDICINE"


def _format_clinic_datetime(dt: datetime, tz_name: str = "Asia/Kolkata") -> tuple[str, str, str]:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt_local = dt.astimezone(tz)
    iso_str = dt_local.isoformat()
    time_str = dt_local.strftime("%I:%M %p").lstrip("0")
    date_str = dt_local.strftime("%A, %d %B %Y")
    return iso_str, time_str, date_str


class ToolExecutor:
    def __init__(
        self,
        session: AsyncSession,
        organization_id: UUID,
        *,
        actor_id: UUID,
        settings: Settings,
        whatsapp: TwilioWhatsAppClient | None = None,
        caller_phone_e164: str | None = None,
        operation_authorizer: Callable[[str, dict[str, Any]], Awaitable[dict[str, object] | None]] | None = None,
        commit_mutations: bool = True,
        booking_source: str = "AI_TEXT",
        booking_consent_channel: str = "AI_TEXT",
        allow_appointment_mutations: bool = True,
    ) -> None:
        self._session = session
        self._organization_id = organization_id
        self._actor_id = actor_id
        self._settings = settings
        self._whatsapp = whatsapp or TwilioWhatsAppClient(settings)
        self._caller_phone = caller_phone_e164
        self._operation_authorizer = operation_authorizer
        self._commit_mutations = commit_mutations
        self._booking_source = booking_source
        self._booking_consent_channel = booking_consent_channel
        self._allow_appointment_mutations = allow_appointment_mutations

    async def _query(self, *args: Any, **kwargs: Any) -> Any:
        from app.observability.telemetry import span_scope
        from app.voice import presentation

        started_at = time.monotonic()
        query_id = secrets.token_hex(12)
        presentation.emit("database_started", "database", "Backend query sent to Supabase",
                          query_id=query_id)
        with span_scope("database.query", {"db.system": "postgresql", "db.operation": "execute"}):
            try:
                result = await self._session.execute(*args, **kwargs)
            except BaseException:
                presentation.emit("database_failed", "database", "Database query failed",
                                  query_id=query_id,
                                  details={"duration_ms": round((time.monotonic() - started_at) * 1000)})
                raise
        presentation.emit("database_completed", "database", "Supabase returned to backend",
                          query_id=query_id,
                          details={"duration_ms": round((time.monotonic() - started_at) * 1000)})
        return result

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, object]:
        from app.voice import presentation

        with presentation.tool_scope(name, presentation.tool_context.get()[1]):
            return await self._execute_observed(name, arguments)

    async def _execute_observed(self, name: str, arguments: dict[str, Any]) -> dict[str, object]:
        from app.voice import presentation

        title = presentation.TOOLS.get(name, "Executing a controlled tool")
        started_at = time.monotonic()
        presentation.emit("tool_started", "tools", title,
                          tool=name if name in presentation.TOOLS else "controlled_tool",
                          details=presentation.safe_arguments(arguments))
        try:
            result = await self._execute(name, arguments)
        except BaseException:
            presentation.emit("tool_failed", "tools", "Tool did not complete",
                              details={"duration_ms": round((time.monotonic() - started_at) * 1000)})
            raise
        safe_details = presentation.safe_result(result)
        safe_details["duration_ms"] = round((time.monotonic() - started_at) * 1000)
        presentation.emit(
            "tool_completed" if result.get("ok") is not False else "tool_failed",
            "tools", "Tool returned a result" if result.get("ok") is not False else "Request rejected",
            tool=name if name in presentation.TOOLS else "controlled_tool",
            details=safe_details,
        )
        if name == "lookup_caller_family":
            presentation.emit("identity_resolved", "identity", "Mobile profile lookup completed",
                              details={"identity_status": "Recognized caller" if result.get("recognized")
                                       else "New caller" if result.get("ok") is True else "Lookup unavailable"})
        if self._commit_mutations and not arguments.get("_voice_preview"):
            presentation.committed(name, result)
        if name == "prepare_booking_offer" and result.get("ok") is True:
            presentation.emit("proposal", "consent", "Appointment proposed; confirmation required")
        return result

    async def _execute(self, name: str, arguments: dict[str, Any]) -> dict[str, object]:
        if name in {"confirm_booking_offer", "cancel_appointment", "reschedule_appointment"} and not self._allow_appointment_mutations:
            return {
                "ok": False,
                "error": "This voice channel cannot verify completed readback. Please use reception or the secure voice flow to make appointment changes.",
            }
        if name in {"confirm_booking_offer", "cancel_appointment", "reschedule_appointment"}:
            authorization = await self._authorize_voice_operation(name, arguments)
            if authorization is not None:
                return authorization
        if name == "suggest_department":
            return await self._suggest_department(arguments)
        if name == "search_availability":
            return await self._search_availability(arguments)
        if name == "lookup_caller_family":
            return await self._lookup_caller_family(arguments)
        if name == "start_phone_verification":
            return await self._start_phone_verification(arguments)
        if name == "verify_phone_code":
            return await self._verify_phone_code(arguments)
        if name == "list_upcoming_appointments":
            return await self._list_upcoming_appointments(arguments)
        if name == "prepare_booking_offer":
            return await self._prepare_booking_offer(arguments)
        if name == "confirm_booking_offer":
            return await self._confirm_booking_offer(arguments)
        if name == "get_clinic_information":
            return await self._get_clinic_information(arguments)
        if name == "cancel_appointment":
            return await self._cancel_appointment(arguments)
        if name == "reschedule_appointment":
            return await self._reschedule_appointment(arguments)
        return {"ok": False, "error": "Tool is not allowed."}

    async def _authorize_voice_operation(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, object] | None:
        if self._operation_authorizer is None:
            return None
        return await self._operation_authorizer(name, arguments)

    async def _suggest_department(self, arguments: dict[str, Any]) -> dict[str, object]:
        problem = " ".join(str(arguments.get("problem_description", "")).casefold().split())
        if len(problem) < 3:
            return {"ok": False, "error": "Please briefly describe the problem."}

        result = await self._query(
            text(
                """
                select department.name as department_name,
                       assignment.display_name as doctor_name
                from public.departments department
                left join public.doctor_assignments assignment
                  on assignment.organization_id=department.organization_id
                 and assignment.department_id=department.id
                 and assignment.active
                where department.organization_id=:org and department.active
                order by department.name, assignment.display_name
                """
            ),
            {"org": self._organization_id},
        )
        rows = list(result.mappings())
        departments = list(dict.fromkeys(str(row["department_name"]) for row in rows))
        if not departments:
            return {"ok": False, "error": "No active clinic departments were found."}

        route = _problem_route(problem)
        if route == "URGENT":
            return {
                "ok": True,
                "urgent_warning": True,
                "suggested_department": None,
                "doctors": [],
                "available_departments": departments,
                "message": (
                    "This description includes a warning sign that may need urgent medical "
                    "attention. Do not continue ordinary appointment routing."
                ),
            }

        preferred = "Gynae" if route == "GYNAE" else "General Medicine"
        suggested = _best_department_match(preferred, departments)
        if suggested is None:
            suggested = departments[0] if len(departments) == 1 else None
        doctors = [
            str(row["doctor_name"])
            for row in rows
            if row["doctor_name"] and row["department_name"] == suggested
        ]
        return {
            "ok": True,
            "urgent_warning": False,
            "suggested_department": suggested,
            "doctors": doctors,
            "available_departments": departments,
            "routing_confidence": "LIMITED",
            "message": (
                "This is an administrative suggestion based on the caller's words, not a "
                "diagnosis or urgency assessment."
            ),
        }

    async def _authorize_database_session(self) -> None:
        await self._query(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(self._actor_id)},
        )

    def _code_digest(self, code: str) -> str | None:
        pepper = self._settings.verification_code_pepper
        if not pepper:
            return None
        return hmac.new(
            pepper.encode(),
            code.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _sign_offer(self, payload: dict[str, object]) -> str | None:
        pepper = self._settings.verification_code_pepper
        if not pepper:
            return None
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        encoded = base64.urlsafe_b64encode(body).decode().rstrip("=")
        signature = hmac.new(
            pepper.encode(),
            f"booking-offer:{encoded}".encode(),
            hashlib.sha256,
        ).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return f"{encoded}.{encoded_signature}"

    def _verify_offer(self, token: str) -> dict[str, object] | None:
        pepper = self._settings.verification_code_pepper
        if not pepper:
            return None
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected = hmac.new(
                pepper.encode(),
                f"booking-offer:{encoded}".encode(),
                hashlib.sha256,
            ).digest()
            supplied = base64.urlsafe_b64decode(
                supplied_signature + "=" * (-len(supplied_signature) % 4)
            )
            if not hmac.compare_digest(expected, supplied):
                return None
            body = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            payload = json.loads(body)
        except (ValueError, TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    async def _search_availability(self, arguments: dict[str, Any]) -> dict[str, object]:
        try:
            from_at = datetime.fromisoformat(str(arguments["from_at"]).replace("Z", "+00:00"))
            to_at = datetime.fromisoformat(str(arguments["to_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            return {"ok": False, "error": "Dates must be valid ISO 8601 datetimes."}
        if to_at <= from_at:
            return {"ok": False, "error": "The end time must be after the start time."}

        requested_doctor = str(arguments.get("doctor_name") or "").strip()
        requested_department = str(arguments.get("department_name") or "").strip()
        resolved_doctor: str | None = None
        ambiguous_candidates: list[str] = []
        resolved_department: str | None = None
        if requested_doctor:
            doctors_result = await self._query(
                text(
                    """
                    select display_name from public.doctor_assignments
                    where organization_id=:org and active
                    order by display_name
                    """
                ),
                {"org": self._organization_id},
            )
            available_doctors = [str(row["display_name"]) for row in doctors_result.mappings()]
            resolved_doctor, ambiguous_candidates = _match_doctor(requested_doctor, available_doctors)
            if ambiguous_candidates:
                return {
                    "ok": False,
                    "error": "AMBIGUOUS_DOCTOR",
                    "message": (
                        f"Multiple doctors match '{requested_doctor}': "
                        f"{', '.join(ambiguous_candidates)}. "
                        "Please specify which doctor you would like to see."
                    ),
                    "candidates": ambiguous_candidates,
                }
            if resolved_doctor is None:
                return {
                    "ok": False,
                    "error": "That doctor was not found.",
                    "available_doctors": available_doctors,
                }
        if requested_department:
            departments_result = await self._query(
                text(
                    """
                    select name from public.departments
                    where organization_id=:org and active
                    order by name
                    """
                ),
                {"org": self._organization_id},
            )
            available_departments = [
                str(row["name"]) for row in departments_result.mappings()
            ]
            resolved_department = _best_department_match(
                requested_department, available_departments
            )
            if resolved_department is None:
                return {
                    "ok": False,
                    "error": "That department was not found.",
                    "available_departments": available_departments,
                }

        result = await self._query(
            text(
                """
                select s.id, s.assignment_id, s.booking_mode, s.starts_at, s.ends_at,
                       s.max_patients, s.timezone, s.booking_cutoff_minutes,
                       da.display_name as doctor_name, d.name as department_name,
                       l.name as location_name,
                       count(a.id) filter (
                           where a.status in ('PAYMENT_PENDING','CONFIRMED','COMPLETED','NO_SHOW')
                       ) as occupied
                from public.appointment_sessions s
                join public.doctor_assignments da
                  on da.organization_id=s.organization_id and da.id=s.assignment_id and da.active
                join public.departments d
                  on d.organization_id=da.organization_id and d.id=da.department_id and d.active
                join public.locations l
                  on l.organization_id=da.organization_id and l.id=da.location_id and l.active
                left join public.appointments a
                  on a.organization_id=s.organization_id and a.session_id=s.id
                where s.organization_id=:org and s.starts_at >= :from_at and s.starts_at < :to_at
                  and s.status in ('SCHEDULED', 'OPEN')
                  and s.starts_at - (s.booking_cutoff_minutes * interval '1 minute') > now()
                  and (
                    cast(:doctor_name as text) is null
                    or da.display_name = cast(:doctor_name as text)
                  )
                  and (
                    cast(:department_name as text) is null
                    or d.name = cast(:department_name as text)
                  )
                group by s.id, s.timezone, s.booking_cutoff_minutes, da.display_name, d.name, l.name
                having s.booking_mode='EXACT_TIME' or count(a.id) filter (
                    where a.status in ('PAYMENT_PENDING','CONFIRMED','COMPLETED','NO_SHOW')
                ) < s.max_patients
                order by s.starts_at
                limit 12
                """
            ),
            {
                "org": self._organization_id,
                "from_at": from_at,
                "to_at": to_at,
                "doctor_name": resolved_doctor,
                "department_name": resolved_department,
            },
        )
        sessions = []
        for row in result.mappings():
            item = dict(row)
            reservation_slot_id: str | None = None
            available_places: int | None = None
            if item["booking_mode"] == "EXACT_TIME":
                slot_result = await self._query(
                    text(
                        """
                        select slot.id, slot.starts_at, slot.ends_at
                        from public.appointment_slots slot
                        where slot.organization_id=:org and slot.session_id=:session
                        and slot.bookable
                        and not exists (
                            select 1 from public.appointments appointment
                            where appointment.organization_id=slot.organization_id
                            and appointment.slot_id=slot.id
                            and appointment.status in (
                                'PAYMENT_PENDING','CONFIRMED','COMPLETED','NO_SHOW'
                            )
                        )
                        order by slot.starts_at
                        limit 12
                        """
                    ),
                    {"org": self._organization_id, "session": item["id"]},
                )
                available_slots = list(slot_result.mappings())
                reservation_slot_id = (
                    str(available_slots[0]["id"]) if available_slots else None
                )
                available_places = len(available_slots)
            else:
                available_places = int(item["max_patients"]) - int(item["occupied"])
            tz_name = str(item.get("timezone") or "Asia/Kolkata")
            iso_start, time_start, date_start = _format_clinic_datetime(item["starts_at"], tz_name)
            iso_end, time_end, _ = _format_clinic_datetime(item["ends_at"], tz_name)
            readable_time = f"{time_start} to {time_end} IST"

            sessions.append(
                {
                    "session_id": str(item["id"]),
                    "assignment_id": str(item["assignment_id"]),
                    "doctor_name": item["doctor_name"],
                    "department": item["department_name"],
                    "location": item["location_name"],
                    "session_date": date_start,
                    "session_time": readable_time,
                    "starts_at": iso_start,
                    "ends_at": iso_end,
                    "timezone": tz_name,
                    "booking_mode": "SESSION_WINDOW",
                    "available_places": available_places,
                    "reservation_slot_id": reservation_slot_id,
                }
            )
        return {
            "ok": True,
            "matched_doctor": resolved_doctor,
            "matched_department": resolved_department,
            "sessions": sessions,
        }

    async def _lookup_caller_family(self, arguments: dict[str, Any]) -> dict[str, object]:
        phone = str(arguments.get("phone_e164", "")).strip()
        if self._caller_phone is not None and phone != self._caller_phone:
            return {"ok": False, "error": "Access denied: caller phone mismatch."}
        if not phone.startswith("+") or not phone[1:].isdigit() or not 8 <= len(phone[1:]) <= 15:
            return {"ok": False, "error": "A valid E.164 mobile number is required."}
        result = await self._query(
            text(
                """
                select c.display_name as caller_name,
                       coalesce(jsonb_agg(jsonb_build_object(
                         'patient_name', p.display_name,
                         'relationship', link.relationship
                       ) order by p.display_name) filter (where p.id is not null), '[]'::jsonb) as patients
                from public.contact_phones cp
                join public.contacts c
                  on c.organization_id=cp.organization_id and c.id=cp.contact_id
                left join public.patient_contacts link
                  on link.organization_id=c.organization_id and link.contact_id=c.id
                 and link.relationship_status='RECORDED'
                left join public.patients p
                  on p.organization_id=link.organization_id and p.id=link.patient_id and p.status='ACTIVE'
                where cp.organization_id=:org and cp.phone_e164=:phone
                  and cp.status='ACTIVE' and c.status='ACTIVE'
                group by c.id, c.display_name
                """
            ),
            {"org": self._organization_id, "phone": phone},
        )
        row = result.mappings().one_or_none()
        if row is None:
            return {"ok": True, "recognized": False}
        return {
            "ok": True,
            "recognized": True,
            "caller_name": row["caller_name"],
            "family_profiles": json.loads(json.dumps(row["patients"])),
        }

    async def _start_phone_verification(self, arguments: dict[str, Any]) -> dict[str, object]:
        phone = str(arguments.get("phone_e164", "")).strip()
        if self._caller_phone is not None and phone != self._caller_phone:
            return {"ok": False, "error": "Access denied: caller phone mismatch."}
        if not self._valid_phone(phone):
            return {"ok": False, "error": "A valid E.164 mobile number is required."}
        if not self._settings.verification_code_pepper:
            return {"ok": False, "error": "Verification is not configured."}
        phone_result = await self._query(
            text(
                """
                select id, version from public.contact_phones
                where organization_id=:org and phone_e164=:phone and status='ACTIVE'
                """
            ),
            {"org": self._organization_id, "phone": phone},
        )
        phone_row = phone_result.mappings().one_or_none()
        if phone_row is None:
            return {
                "ok": True,
                "sent": False,
                "message": "No saved caller is available for verification.",
            }

        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = self._code_digest(code)
        assert digest is not None
        await self._authorize_database_session()
        challenge_result = await self._query(
            text(
                """
                select * from public.issue_verification_challenge(
                    :org,:phone_id,:phone_version,:digest,null,300
                )
                """
            ),
            {
                "org": self._organization_id,
                "phone_id": phone_row["id"],
                "phone_version": phone_row["version"],
                "digest": digest,
            },
        )
        challenge = challenge_result.mappings().one()
        delivery = await self._whatsapp.send(
            phone,
            f"Your Geeta Medicine verification code is {code}. It expires in 5 minutes.",
        )
        if self._commit_mutations:
            await self._session.commit()
        return {
            "ok": True,
            "sent": True,
            "challenge_id": str(challenge["challenge_id"]),
            "expires_at": challenge["expires_at"].isoformat(),
            "delivery_status": delivery.status,
        }

    async def _verify_phone_code(self, arguments: dict[str, Any]) -> dict[str, object]:
        code = str(arguments.get("code", "")).strip()
        try:
            challenge_id = UUID(str(arguments.get("challenge_id", "")))
        except ValueError:
            return {"ok": False, "error": "A valid verification challenge is required."}
        if len(code) != 6 or not code.isdigit():
            return {"ok": False, "error": "Enter the six-digit verification code."}
        digest = self._code_digest(code)
        if digest is None:
            return {"ok": False, "error": "Verification is not configured."}
        await self._authorize_database_session()
        result = await self._query(
            text(
                """
                select * from public.verify_verification_challenge(
                    :org,:challenge,:digest,600
                )
                """
            ),
            {
                "org": self._organization_id,
                "challenge": challenge_id,
                "digest": digest,
            },
        )
        verification = dict(result.mappings().one())
        if self._commit_mutations:
            await self._session.commit()
        verification["ok"] = True
        if verification.get("verified_until") is not None:
            verification["verified_until"] = verification["verified_until"].isoformat()
        return verification

    async def _list_upcoming_appointments(self, arguments: dict[str, Any]) -> dict[str, object]:
        phone = str(arguments.get("phone_e164", "")).strip()
        if self._caller_phone is not None and phone != self._caller_phone:
            return {"ok": False, "error": "Access denied: caller phone mismatch."}
        challenge_id_raw = arguments.get("challenge_id")
        if not self._valid_phone(phone):
            return {"ok": False, "error": "A valid E.164 mobile number is required."}

        challenge_id: UUID | None = None
        if challenge_id_raw:
            try:
                challenge_id = UUID(str(challenge_id_raw))
            except ValueError:
                return {"ok": False, "error": "Invalid verification challenge."}

        if challenge_id is not None:
            query = """
                select appointment.booking_reference, patient.display_name as patient_name,
                       assignment.display_name as doctor_name, department.name as department_name,
                       location.name as location_name, appointment_session.booking_mode,
                       coalesce(slot.starts_at, appointment_session.starts_at) as scheduled_at,
                       appointment_session.ends_at as session_ends_at, appointment.token_number,
                       appointment.status
                from public.verification_challenges challenge
                join public.contact_phones phone
                  on phone.organization_id=challenge.organization_id
                 and phone.id=challenge.contact_phone_id
                 and phone.version=challenge.phone_version
                 and phone.status='ACTIVE'
                join public.appointment_contact_permissions permission
                  on permission.organization_id=challenge.organization_id
                 and permission.contact_id=phone.contact_id
                 and permission.can_view and permission.revoked_at is null
                join public.appointments appointment
                  on appointment.organization_id=permission.organization_id
                 and appointment.id=permission.appointment_id
                join public.patients patient
                  on patient.organization_id=appointment.organization_id
                 and patient.id=appointment.patient_id
                join public.appointment_sessions appointment_session
                  on appointment_session.organization_id=appointment.organization_id
                 and appointment_session.id=appointment.session_id
                left join public.appointment_slots slot
                  on slot.organization_id=appointment.organization_id
                 and slot.id=appointment.slot_id
                join public.doctor_assignments assignment
                  on assignment.organization_id=appointment.organization_id
                 and assignment.id=appointment.assignment_id
                join public.departments department
                  on department.organization_id=assignment.organization_id
                 and department.id=assignment.department_id
                join public.locations location
                  on location.organization_id=assignment.organization_id
                 and location.id=assignment.location_id
                where challenge.organization_id=:org and challenge.id=:challenge
                  and challenge.status='VERIFIED' and challenge.verified_until > now()
                  and phone.phone_e164=:phone
                  and appointment.status in ('PAYMENT_PENDING','CONFIRMED')
                  and appointment_session.ends_at >= now() - interval '2 hours'
                order by coalesce(slot.starts_at, appointment_session.starts_at)
                limit 10
            """
            params = {"org": self._organization_id, "challenge": challenge_id, "phone": phone}
        else:
            query = """
                select appointment.booking_reference, patient.display_name as patient_name,
                       assignment.display_name as doctor_name, department.name as department_name,
                       location.name as location_name, appointment_session.booking_mode,
                       coalesce(slot.starts_at, appointment_session.starts_at) as scheduled_at,
                       appointment_session.ends_at as session_ends_at, appointment.token_number,
                       appointment.status
                from public.contact_phones phone
                join public.appointment_contact_permissions permission
                  on permission.organization_id=phone.organization_id
                 and permission.contact_id=phone.contact_id
                 and permission.can_view and permission.revoked_at is null
                join public.appointments appointment
                  on appointment.organization_id=permission.organization_id
                 and appointment.id=permission.appointment_id
                join public.patients patient
                  on patient.organization_id=appointment.organization_id
                 and patient.id=appointment.patient_id
                join public.appointment_sessions appointment_session
                  on appointment_session.organization_id=appointment.organization_id
                 and appointment_session.id=appointment.session_id
                left join public.appointment_slots slot
                  on slot.organization_id=appointment.organization_id
                 and slot.id=appointment.slot_id
                join public.doctor_assignments assignment
                  on assignment.organization_id=appointment.organization_id
                 and assignment.id=appointment.assignment_id
                join public.departments department
                  on department.organization_id=assignment.organization_id
                 and department.id=assignment.department_id
                join public.locations location
                  on location.organization_id=assignment.organization_id
                 and location.id=assignment.location_id
                where phone.organization_id=:org
                  and phone.phone_e164=:phone
                  and phone.status='ACTIVE'
                  and appointment.status in ('PAYMENT_PENDING','CONFIRMED')
                  and appointment_session.ends_at >= now() - interval '2 hours'
                order by coalesce(slot.starts_at, appointment_session.starts_at)
                limit 10
            """
            params = {"org": self._organization_id, "phone": phone}

        result = await self._query(text(query), params)
        appointments = []
        for row in result.mappings():
            item = dict(row)
            tz_name = "Asia/Kolkata"
            iso_start, time_start, date_start = _format_clinic_datetime(item["scheduled_at"], tz_name)
            iso_end, time_end, _ = _format_clinic_datetime(item["session_ends_at"], tz_name)
            item["scheduled_at"] = iso_start
            item["session_ends_at"] = iso_end
            item["readable_date"] = date_start
            item["readable_time"] = f"{time_start} to {time_end} IST"
            appointments.append(item)
        return {"ok": True, "appointments": appointments}

    async def _prepare_booking_offer(self, arguments: dict[str, Any]) -> dict[str, object]:
        phone = str(arguments.get("phone_e164", "")).strip()
        if self._caller_phone is not None and phone != self._caller_phone:
            return {"ok": False, "error": "Access denied: caller phone mismatch."}
        caller_name = str(arguments.get("caller_name", "") or "").strip()
        patient_name = str(arguments.get("patient_name", "")).strip()
        relationship = str(arguments.get("relationship", "")).strip().upper()
        # Conference flow never collects payment; keep the existing due-at-clinic ledger.
        payment_method = "CASH"
        language = str(arguments.get("language", "")).strip()
        create_patient = arguments.get("create_patient_if_missing") is True
        create_caller = arguments.get("create_caller_if_missing") is True
        try:
            session_id = UUID(str(arguments.get("session_id", "")))
            slot_value = arguments.get("slot_id")
            slot_id = UUID(str(slot_value)) if slot_value else None
        except ValueError:
            return {"ok": False, "error": "A valid session and slot selection is required."}
        if not self._valid_phone(phone) or not patient_name:
            return {"ok": False, "error": "Saved caller and patient details are required."}
        if relationship not in {"SELF", "MOTHER", "FATHER", "SPOUSE", "CHILD", "OTHER"}:
            return {"ok": False, "error": "A valid family relationship is required."}
        if language not in {"en", "hi", "en-IN", "hi-IN"}:
            return {"ok": False, "error": "A supported consent language is required."}

        contact_result = await self._query(
            text(
                """
                select phone.id as phone_id, phone.contact_id,
                       contact.display_name as caller_name
                from public.contact_phones phone
                join public.contacts contact
                  on contact.organization_id=phone.organization_id
                 and contact.id=phone.contact_id and contact.status='ACTIVE'
                where phone.organization_id=:org and phone.phone_e164=:phone
                  and phone.status='ACTIVE'
                """
            ),
            {
                "org": self._organization_id,
                "phone": phone,
            },
        )
        contact = contact_result.mappings().one_or_none()
        if contact is None and (not create_caller or not caller_name):
            return {"ok": False, "error": "That saved caller mobile was not found."}
        patient = None
        if contact is not None:
            patient_result = await self._query(
                text(
                    """
                select patient.id as patient_id, patient.display_name as patient_name
                from public.patient_contacts link
                join public.patients patient
                  on patient.organization_id=link.organization_id
                 and patient.id=link.patient_id and patient.status='ACTIVE'
                where link.organization_id=:org and link.contact_id=:contact
                  and link.relationship_status='RECORDED' and link.relationship=:relationship
                  and lower(patient.display_name)=lower(:patient_name)
                order by patient.created_at limit 1
                """
                ),
                {
                    "org": self._organization_id,
                    "contact": contact["contact_id"],
                    "patient_name": patient_name,
                    "relationship": relationship,
                },
            )
            patient = patient_result.mappings().one_or_none()
        if patient is None and not create_patient:
            return {
                "ok": False,
                "error": "That saved patient was not found for this caller and relationship.",
            }

        schedule_result = await self._query(
            text(
                """
                select appointment_session.id as session_id,
                       appointment_session.assignment_id,
                       appointment_session.booking_mode,
                       appointment_session.starts_at as session_starts_at,
                       appointment_session.ends_at as session_ends_at,
                       appointment_session.timezone,
                       assignment.display_name as doctor_name,
                       assignment.fee_minor, assignment.currency,
                       location.name as location_name,
                       slot.id as slot_id, slot.starts_at as slot_starts_at,
                       slot.ends_at as slot_ends_at
                from public.appointment_sessions appointment_session
                join public.doctor_assignments assignment
                  on assignment.organization_id=appointment_session.organization_id
                 and assignment.id=appointment_session.assignment_id and assignment.active
                join public.locations location
                  on location.organization_id=assignment.organization_id
                 and location.id=assignment.location_id and location.active
                left join public.appointment_slots slot
                  on slot.organization_id=appointment_session.organization_id
                 and slot.session_id=appointment_session.id
                 and slot.id=cast(:slot_id as uuid) and slot.bookable
                where appointment_session.organization_id=:org
                  and appointment_session.id=:session
                  and appointment_session.status in ('SCHEDULED','OPEN')
                  and appointment_session.starts_at > now()
                  and appointment_session.starts_at - (appointment_session.booking_cutoff_minutes * interval '1 minute') > now()
                """
            ),
            {
                "org": self._organization_id,
                "session": session_id,
                "slot_id": slot_id,
            },
        )
        schedule = schedule_result.mappings().one_or_none()
        if schedule is None:
            return {"ok": False, "error": "That appointment option is no longer available."}
        if schedule["booking_mode"] == "EXACT_TIME" and schedule["slot_id"] is None:
            return {"ok": False, "error": "Choose an available exact-time slot."}
        if schedule["booking_mode"] == "SESSION_TOKEN" and slot_id is not None:
            return {"ok": False, "error": "Token sessions do not use an exact-time slot."}

        starts_at = schedule["session_starts_at"]
        ends_at = schedule["session_ends_at"]
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        payload: dict[str, object] = {
            "organization_id": str(self._organization_id),
            "actor_id": str(self._actor_id),
            "patient_id": str(patient["patient_id"]) if patient else None,
            "patient_name": patient["patient_name"] if patient else patient_name,
            "relationship": relationship,
            "create_patient": patient is None,
            "caller_name": contact["caller_name"] if contact else caller_name,
            "create_contact": contact is None,
            "contact_id": str(contact["contact_id"]) if contact else None,
            "phone_id": str(contact["phone_id"]) if contact else None,
            "phone_e164": phone,
            "assignment_id": str(schedule["assignment_id"]),
            "fee_minor": schedule["fee_minor"],
            "currency": schedule["currency"],
            "session_id": str(schedule["session_id"]),
            "slot_id": str(schedule["slot_id"]) if schedule["slot_id"] else None,
            "payment_method": payment_method,
            "language": language,
            "expires_at": expires_at.isoformat(),
            "nonce": secrets.token_hex(16),
        }
        token = self._sign_offer(payload)
        if token is None:
            return {"ok": False, "error": "Booking offers are not configured."}
        tz_name = str(schedule.get("timezone") or "Asia/Kolkata")
        iso_start, time_start, date_start = _format_clinic_datetime(starts_at, tz_name)
        iso_end, time_end, _ = _format_clinic_datetime(ends_at, tz_name)
        readable_time = f"{time_start} to {time_end} IST"
        return {
            "ok": True,
            "offer_token": token,
            "offer": {
                "patient_name": patient["patient_name"] if patient else patient_name,
                "relationship": relationship,
                "new_patient_profile": patient is None,
                "doctor_name": schedule["doctor_name"],
                "location_name": schedule["location_name"],
                "booking_mode": "SESSION_WINDOW",
                "session_date": date_start,
                "session_time": readable_time,
                "starts_at": iso_start,
                "ends_at": iso_end,
                "timezone": tz_name,
                "fee_minor": schedule["fee_minor"],
                "currency": schedule["currency"],
                "fee_display": f"{schedule['currency']} {schedule['fee_minor'] / 100:.2f}",
                "payment_method": payment_method,
                "language": language,
                "expires_at": expires_at.isoformat(),
            },
            "instruction": "Read back every offer field and ask for explicit confirmation.",
        }

    async def _confirm_booking_offer(self, arguments: dict[str, Any]) -> dict[str, object]:
        token = str(arguments.get("offer_token", ""))
        offer = self._verify_offer(token)
        if offer is None:
            return {"ok": False, "error": "The booking offer is invalid."}
        try:
            expires_at = datetime.fromisoformat(str(offer["expires_at"]))
            organization_id = UUID(str(offer["organization_id"]))
            actor_id = UUID(str(offer["actor_id"]))
            patient_id = UUID(str(offer["patient_id"])) if offer.get("patient_id") else None
            contact_id = UUID(str(offer["contact_id"])) if offer.get("contact_id") else None
            phone_id = UUID(str(offer["phone_id"])) if offer.get("phone_id") else None
            assignment_id = UUID(str(offer["assignment_id"]))
            session_id = UUID(str(offer["session_id"]))
            slot_id = UUID(str(offer["slot_id"])) if offer.get("slot_id") else None
        except (KeyError, ValueError):
            return {"ok": False, "error": "The booking offer is invalid."}
        if organization_id != self._organization_id or actor_id != self._actor_id:
            return {"ok": False, "error": "The booking offer belongs to another session."}
        if expires_at <= datetime.now(UTC):
            return {"ok": False, "error": "The booking offer expired. Check availability again."}
        payment_method = str(offer.get("payment_method", ""))
        language = str(offer.get("language", ""))
        nonce = str(offer.get("nonce", ""))
        patient_name = str(offer.get("patient_name", "")).strip()
        relationship = str(offer.get("relationship", "")).strip()
        create_patient = offer.get("create_patient") is True
        caller_name = str(offer.get("caller_name", "")).strip()
        phone_e164 = str(offer.get("phone_e164", "")).strip()
        if self._caller_phone is not None and phone_e164 != self._caller_phone:
            return {"ok": False, "error": "Access denied: caller phone mismatch."}
        create_contact = offer.get("create_contact") is True
        if payment_method not in {"CASH", "ONLINE", "UPI"} or not nonce:
            return {"ok": False, "error": "The booking offer is invalid."}
        if patient_id is None and (not create_patient or not patient_name):
            return {"ok": False, "error": "The booking offer is invalid."}
        if (contact_id is None or phone_id is None) and (
            not create_contact or not caller_name or not self._valid_phone(phone_e164)
        ):
            return {"ok": False, "error": "The booking offer is invalid."}

        if offer.get("fee_minor") is not None or offer.get("currency") is not None:
            assignment_result = await self._query(
                text(
                    """
                    select fee_minor, currency from public.doctor_assignments
                    where organization_id=:org and id=:assignment and active
                    """
                ),
                {"org": organization_id, "assignment": assignment_id},
            )
            assignment_row = assignment_result.mappings().one_or_none()
            if assignment_row is None:
                return {"ok": False, "error": "The doctor assignment is no longer active."}
            if (
                offer.get("fee_minor") is not None
                and assignment_row["fee_minor"] != offer.get("fee_minor")
            ) or (
                offer.get("currency") is not None
                and assignment_row["currency"] != offer.get("currency")
            ):
                return {"ok": False, "error": "The consultation fee has changed. Check availability again."}

        request_hash = hashlib.sha256(
            json.dumps(offer, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        await self._authorize_database_session()
        contact_created = False
        if contact_id is None or phone_id is None:
            await self._query(
                text("select pg_advisory_xact_lock(hashtextextended(:identity_key, 0))"),
                {"identity_key": f"{organization_id}:{phone_e164}"},
            )
            existing_phone = await self._query(
                text(
                    """
                    select id, contact_id from public.contact_phones
                    where organization_id=:org and phone_e164=:phone and status='ACTIVE'
                    """
                ),
                {"org": organization_id, "phone": phone_e164},
            )
            phone_row = existing_phone.mappings().one_or_none()
            if phone_row is None:
                created_contact = await self._query(
                    text(
                        """
                        insert into public.contacts (organization_id, display_name, name_source)
                        values (:org,:name,'STATED') returning id
                        """
                    ),
                    {"org": organization_id, "name": caller_name},
                )
                contact_id = created_contact.scalar_one()
                created_phone = await self._query(
                    text(
                        """
                        insert into public.contact_phones
                          (organization_id,contact_id,phone_e164)
                        values (:org,:contact,:phone) returning id
                        """
                    ),
                    {"org": organization_id, "contact": contact_id, "phone": phone_e164},
                )
                phone_id = created_phone.scalar_one()
                contact_created = True
            else:
                contact_id = phone_row["contact_id"]
                phone_id = phone_row["id"]
        assert contact_id is not None
        assert phone_id is not None
        patient_profile_created = False
        if patient_id is None:
            await self._query(
                text("select pg_advisory_xact_lock(hashtextextended(:identity_key, 0))"),
                {
                    "identity_key": (
                        f"{organization_id}:{contact_id}:{relationship}:{patient_name.casefold()}"
                    )
                },
            )
            existing_patient = await self._query(
                text(
                    """
                    select patient.id
                    from public.patient_contacts link
                    join public.patients patient
                      on patient.organization_id=link.organization_id
                     and patient.id=link.patient_id and patient.status='ACTIVE'
                    where link.organization_id=:org and link.contact_id=:contact
                      and link.relationship_status='RECORDED'
                      and link.relationship=:relationship
                      and lower(patient.display_name)=lower(:patient_name)
                    order by patient.created_at limit 1
                    """
                ),
                {
                    "org": organization_id,
                    "contact": contact_id,
                    "relationship": relationship,
                    "patient_name": patient_name,
                },
            )
            patient_id = existing_patient.scalar_one_or_none()
            if patient_id is None:
                created_patient = await self._query(
                    text(
                        """
                        insert into public.patients (organization_id, display_name)
                        values (:org,:patient_name) returning id
                        """
                    ),
                    {"org": organization_id, "patient_name": patient_name},
                )
                patient_id = created_patient.scalar_one()
                patient_profile_created = True
                await self._query(
                    text(
                        """
                        insert into public.patient_contacts (
                          organization_id,patient_id,contact_id,relationship,
                          recorded_by_auth_user_id
                        ) values (:org,:patient,:contact,:relationship,:actor)
                        """
                    ),
                    {
                        "org": organization_id,
                        "patient": patient_id,
                        "contact": contact_id,
                        "relationship": relationship,
                        "actor": actor_id,
                    },
                )
        assert patient_id is not None
        hold_result = await self._query(
            text(
                """
                select * from public.create_simulated_appointment_hold(
                  :org,:patient,:contact,:phone,:assignment,:appointment_session,:slot,
                  :source,:key,:hash,true,:language,:consent_channel
                )
                """
            ),
            {
                "org": organization_id,
                "patient": patient_id,
                "contact": contact_id,
                "phone": phone_id,
                "assignment": assignment_id,
                "appointment_session": session_id,
                "slot": slot_id,
                "key": f"ai-offer:{nonce}",
                "hash": request_hash,
                "language": language,
                "source": self._booking_source,
                "consent_channel": self._booking_consent_channel,
            },
        )
        hold = hold_result.mappings().one()
        appointment_id = hold["appointment_id"]
        await self._query(
            text(
                """
                update public.payment_attempts set payment_method=:method,
                  mode=case when :method='CASH' then 'PAY_AT_CLINIC' else 'SIMULATED' end
                where organization_id=:org and appointment_id=:appointment
                  and status='SIMULATION_PENDING'
                """
            ),
            {
                "method": payment_method,
                "org": organization_id,
                "appointment": appointment_id,
            },
        )
        confirmed_result = await self._query(
            text("select * from public.confirm_simulated_appointment(:org,:appointment)"),
            {"org": organization_id, "appointment": appointment_id},
        )
        confirmed = dict(confirmed_result.mappings().one())
        if payment_method == "CASH":
            await self._query(
                text("""update public.payment_attempts set status='DUE_AT_CLINIC'
                        where organization_id=:org and appointment_id=:appointment
                          and payment_method='CASH'"""),
                {"org": organization_id, "appointment": appointment_id},
            )
        if self._commit_mutations:
            await self._session.commit()
        confirmed.update(
            {
                "ok": True,
                "payment_method": payment_method,
                "payment_status": "DUE_AT_CLINIC" if payment_method == "CASH" else "SIMULATED_SUCCESS",
                "language": language,
                "patient_profile_created": patient_profile_created,
                "caller_profile_created": contact_created,
            }
        )
        return confirmed

    async def _get_clinic_information(self, arguments: dict[str, Any]) -> dict[str, object]:
        topic = str(arguments.get("topic", "all")).casefold().strip()
        org_result = await self._query(
            text(
                """
                select name, organization_type, timezone
                from public.organizations
                where id=:org and status='ACTIVE'
                """
            ),
            {"org": self._organization_id},
        )
        org_row = org_result.mappings().one_or_none()
        org_name = str(org_row["name"]) if org_row else "Clinic"
        timezone = str(org_row["timezone"]) if org_row else "Asia/Kolkata"

        locations_result = await self._query(
            text(
                """
                select name, address
                from public.locations
                where organization_id=:org and active
                order by name
                """
            ),
            {"org": self._organization_id},
        )
        locations = [
            {"name": str(r["name"]), "address": str(r["address"] or "")}
            for r in locations_result.mappings()
        ]

        departments_result = await self._query(
            text(
                """
                select name
                from public.departments
                where organization_id=:org and active
                order by name
                """
            ),
            {"org": self._organization_id},
        )
        departments = [str(r["name"]) for r in departments_result.mappings()]

        info: dict[str, object] = {
            "ok": True,
            "clinic_name": org_name,
            "timezone": timezone,
        }

        if topic in {"all", "address", "contact"}:
            info["locations"] = locations
        if topic in {"all", "timings"}:
            info["departments"] = departments
            info["operating_hours_note"] = f"Clinic operates according to scheduled sessions ({timezone})."
        if topic in {"all", "emergency"}:
            info["emergency_policy"] = (
                "For life-threatening emergencies, chest pain, difficulty breathing, or severe trauma, "
                "please go to the nearest emergency room immediately or dial 112 / 102."
            )
        if topic in {"all", "payment_policy"}:
            info["payment_modes"] = ["CASH", "PAY_AT_CLINIC"]
            info["payment_policy"] = (
                "Consultation fees are collected at the clinic desk upon arrival. No advance online payment is required."
            )
        return info

    async def _cancel_appointment(self, arguments: dict[str, Any]) -> dict[str, object]:
        ref = str(arguments.get("booking_reference", "")).strip().upper()
        reason = str(arguments.get("reason", "Cancelled by caller via telephone")).strip()
        if not ref:
            return {"ok": False, "error": "Booking reference is required to cancel an appointment."}

        await self._authorize_database_session()

        find_query = """
            select appointment.id, appointment.version, appointment.status,
                   appointment.booking_reference, appointment.token_number,
                   patient.display_name as patient_name,
                   assignment.display_name as doctor_name
            from public.appointments appointment
            join public.patients patient
              on patient.organization_id = appointment.organization_id
             and patient.id = appointment.patient_id
            join public.doctor_assignments assignment
              on assignment.organization_id = appointment.organization_id
             and assignment.id = appointment.assignment_id
            where appointment.organization_id = :org
              and upper(appointment.booking_reference) = :ref
        """
        params: dict[str, Any] = {"org": self._organization_id, "ref": ref}

        if self._caller_phone:
            auth_check = await self._query(
                text("""
                    select 1
                    from public.appointments appointment
                    join public.appointment_contact_permissions permission
                      on permission.organization_id = appointment.organization_id
                     and permission.appointment_id = appointment.id
                     and permission.can_manage and permission.revoked_at is null
                    join public.contact_phones phone
                      on phone.organization_id = permission.organization_id
                     and phone.contact_id = permission.contact_id
                     and phone.status = 'ACTIVE'
                    where appointment.organization_id = :org
                      and upper(appointment.booking_reference) = :ref
                      and phone.phone_e164 = :phone
                """),
                {"org": self._organization_id, "ref": ref, "phone": self._caller_phone},
            )
            if auth_check.scalar_one_or_none() is None:
                return {
                    "ok": False,
                    "error": "Access denied: this appointment does not belong to the verified caller number.",
                }

        row_result = await self._query(text(find_query), params)
        row = row_result.mappings().one_or_none()
        if row is None:
            return {"ok": False, "error": f"Appointment with reference {ref} was not found."}

        if row["status"] == "CANCELLED":
            return {
                "ok": True,
                "already_cancelled": True,
                "status": "CANCELLED",
                "booking_reference": row["booking_reference"],
                "patient_name": row["patient_name"],
                "doctor_name": row["doctor_name"],
                "message": f"Appointment {row['booking_reference']} is already cancelled.",
            }

        if row["status"] not in ("PAYMENT_PENDING", "CONFIRMED"):
            return {
                "ok": False,
                "error": f"Appointment {row['booking_reference']} cannot be cancelled in status {row['status']}.",
            }

        if arguments.get("_voice_preview") is True:
            return {
                "ok": True, "status": "CANCEL_PREVIEW", "booking_reference": row["booking_reference"],
                "patient_name": row["patient_name"], "doctor_name": row["doctor_name"],
            }

        cancel_res = await self._query(
            text("select * from public.cancel_appointment(:org, :appointment, :version, :reason)"),
            {
                "org": self._organization_id,
                "appointment": row["id"],
                "version": row["version"],
                "reason": reason,
            },
        )
        cancelled = dict(cancel_res.mappings().one())
        if self._commit_mutations:
            await self._session.commit()
        return {
            "ok": True,
            "status": "CANCELLED",
            "appointment_id": str(row["id"]),
            "booking_reference": cancelled["booking_reference"],
            "patient_name": row["patient_name"],
            "doctor_name": row["doctor_name"],
            "version": cancelled["version"],
            "message": f"Appointment {cancelled['booking_reference']} for {row['patient_name']} has been cancelled.",
        }

    async def _reschedule_appointment(self, arguments: dict[str, Any]) -> dict[str, object]:
        ref = str(arguments.get("booking_reference", "")).strip().upper()
        new_session_id_raw = arguments.get("new_session_id")
        new_slot_id_raw = arguments.get("new_slot_id")

        if not ref:
            return {"ok": False, "error": "Booking reference is required."}
        if not new_session_id_raw:
            return {"ok": False, "error": "Target session ID is required."}

        try:
            new_session_id = UUID(str(new_session_id_raw))
            new_slot_id = UUID(str(new_slot_id_raw)) if new_slot_id_raw else None
        except ValueError:
            return {"ok": False, "error": "Invalid session or slot UUID."}

        await self._authorize_database_session()

        find_query = """
            select appointment.id, appointment.version, appointment.status,
                   appointment.booking_reference, appointment.session_id,
                   appointment.slot_id, appointment.assignment_id,
                   patient.display_name as patient_name,
                   assignment.display_name as doctor_name
            from public.appointments appointment
            join public.patients patient
              on patient.organization_id = appointment.organization_id
             and patient.id = appointment.patient_id
            join public.doctor_assignments assignment
              on assignment.organization_id = appointment.organization_id
             and assignment.id = appointment.assignment_id
            where appointment.organization_id = :org
              and upper(appointment.booking_reference) = :ref
        """
        row_result = await self._query(
            text(find_query), {"org": self._organization_id, "ref": ref}
        )
        row = row_result.mappings().one_or_none()
        if row is None:
            return {"ok": False, "error": f"Appointment {ref} was not found."}

        if self._caller_phone:
            auth_check = await self._query(
                text("""
                    select 1
                    from public.appointments appointment
                    join public.appointment_contact_permissions permission
                      on permission.organization_id = appointment.organization_id
                     and permission.appointment_id = appointment.id
                     and permission.can_manage and permission.revoked_at is null
                    join public.contact_phones phone
                      on phone.organization_id = permission.organization_id
                     and phone.contact_id = permission.contact_id
                     and phone.status = 'ACTIVE'
                    where appointment.organization_id = :org
                      and upper(appointment.booking_reference) = :ref
                      and phone.phone_e164 = :phone
                """),
                {"org": self._organization_id, "ref": ref, "phone": self._caller_phone},
            )
            if auth_check.scalar_one_or_none() is None:
                return {
                    "ok": False,
                    "error": "Access denied: this appointment does not belong to the verified caller number.",
                }

        if row["status"] != "CONFIRMED":
            return {
                "ok": False,
                "error": f"Only confirmed appointments can be rescheduled. Current status is {row['status']}.",
            }

        if row["session_id"] == new_session_id and row["slot_id"] == new_slot_id:
            return {
                "ok": True,
                "already_scheduled": True,
                "status": "CONFIRMED",
                "booking_reference": row["booking_reference"],
                "patient_name": row["patient_name"],
                "doctor_name": row["doctor_name"],
                "message": f"Appointment {row['booking_reference']} is already scheduled for this session.",
            }

        target_res = await self._query(
            text("""
                select s.id, s.starts_at, s.ends_at, s.status, s.booking_mode,
                       s.max_patients, s.booking_cutoff_minutes, s.assignment_id,
                       a.display_name as doctor_name, l.name as location_name
                from public.appointment_sessions s
                join public.doctor_assignments a
                  on a.organization_id = s.organization_id and a.id = s.assignment_id
                join public.locations l
                  on l.organization_id = a.organization_id and l.id = a.location_id
                where s.organization_id = :org and s.id = :session
                  and a.active and l.active
            """),
            {"org": self._organization_id, "session": new_session_id},
        )
        target = target_res.mappings().one_or_none()
        if target is None or target["status"] not in ("SCHEDULED", "OPEN"):
            return {"ok": False, "error": "The requested target session is not available."}

        now_dt = datetime.now(UTC)
        cutoff_margin = timedelta(minutes=target["booking_cutoff_minutes"])
        if target["starts_at"] - cutoff_margin <= now_dt:
            return {"ok": False, "error": "The booking cutoff for this session has already passed."}

        occ_res = await self._query(
            text("""
                select count(*) from public.appointments
                where organization_id = :org and session_id = :session
                  and status in ('PAYMENT_PENDING', 'CONFIRMED', 'COMPLETED', 'NO_SHOW')
            """),
            {"org": self._organization_id, "session": new_session_id},
        )
        occupancy = occ_res.scalar_one()
        if target["max_patients"] and occupancy >= target["max_patients"]:
            return {"ok": False, "error": "The requested session is full. Please choose another session."}

        if arguments.get("_voice_preview") is True:
            return {
                "ok": True, "status": "RESCHEDULE_PREVIEW", "booking_reference": row["booking_reference"],
                "patient_name": row["patient_name"], "doctor_name": target["doctor_name"],
                "starts_at": target["starts_at"], "ends_at": target["ends_at"],
                "location_name": target["location_name"],
            }

        resched_res = await self._query(
            text("select * from public.reschedule_appointment(:org, :appointment, :version, :new_session, :new_slot)"),
            {
                "org": self._organization_id,
                "appointment": row["id"],
                "version": row["version"],
                "new_session": new_session_id,
                "new_slot": new_slot_id,
            },
        )
        replacement = dict(resched_res.mappings().one())
        if self._commit_mutations:
            await self._session.commit()
        return {
            "ok": True,
            "status": "RESCHEDULED",
            "old_appointment_id": str(replacement["old_appointment_id"]),
            "replacement_appointment_id": str(replacement["replacement_appointment_id"]),
            "replacement_reference": replacement["replacement_reference"],
            "replacement_token": replacement["replacement_token"],
            "patient_name": row["patient_name"],
            "doctor_name": target["doctor_name"],
            "message": (
                f"Appointment rescheduled to {replacement['replacement_reference']} "
                f"with {target['doctor_name']}. Token number: {replacement['replacement_token']}."
            ),
        }

    @staticmethod
    def _valid_phone(phone: str) -> bool:
        return phone.startswith("+") and phone[1:].isdigit() and 8 <= len(phone[1:]) <= 15
