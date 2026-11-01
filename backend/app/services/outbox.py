"""Durable appointment-notification delivery through the transactional outbox."""

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApiError
from app.integrations.twilio import TwilioWhatsAppClient

logger = structlog.get_logger()


def _message(job_type: str, appointment: dict[str, Any]) -> str:
    reference = str(appointment["booking_reference"])
    patient = str(appointment["patient_name"])
    doctor = str(appointment["doctor_name"])
    starts_at = str(appointment["starts_at"])
    if job_type == "APPOINTMENT_CANCELLED":
        return f"Your appointment {reference} for {patient} with {doctor} has been cancelled."
    if job_type == "APPOINTMENT_RESCHEDULED":
        return (
            f"Your appointment is rescheduled. Reference: {reference}. "
            f"{patient} will see {doctor} at {starts_at}."
        )
    return (
        f"Your appointment is confirmed. Reference: {reference}. "
        f"{patient} will see {doctor} at {starts_at}."
    )


async def dispatch_outbox_once(
    session: AsyncSession, settings: Settings, *, limit: int = 10
) -> int:
    """Deliver a leased batch, retaining failures for retry rather than losing them."""
    if not settings.twilio_whatsapp_configured:
        return 0
    client = TwilioWhatsAppClient(settings)
    delivered = 0
    for _ in range(limit):
        claimed = await session.execute(text("select * from public.claim_outbox_jobs(1, 60)"))
        job = claimed.mappings().one_or_none()
        # Publish ownership before contacting the provider. Claim each job just
        # before sending so later jobs cannot sit in an expiring batch lease.
        await session.commit()
        if job is None:
            break
        job_id = job["id"]
        lease_token = job["lease_token"]
        try:
            appointment_result = await session.execute(
                text(
                    """select a.booking_reference, p.display_name as patient_name,
                              d.display_name as doctor_name, s.starts_at, phone.phone_e164
                       from public.appointments a
                       join public.patients p
                         on p.organization_id=a.organization_id and p.id=a.patient_id
                       join public.doctor_assignments d
                         on d.organization_id=a.organization_id and d.id=a.assignment_id
                       join public.appointment_sessions s
                         on s.organization_id=a.organization_id and s.id=a.session_id
                       join public.contact_phones phone on phone.organization_id=a.organization_id
                         and phone.id=a.notification_contact_phone_id
                       where a.organization_id=:org and a.id=:appointment
                         and phone.status='ACTIVE' and phone.messaging_consent=true"""
                ),
                {"org": job["organization_id"], "appointment": job["aggregate_id"]},
            )
            appointment = appointment_result.mappings().one_or_none()
            if appointment is None:
                raise ApiError(
                    "NOTIFICATION_RECIPIENT_UNAVAILABLE",
                    "No consenting notification phone exists.",
                    409,
                )
            await client.send(
                str(appointment["phone_e164"]),
                _message(str(job["job_type"]), dict(appointment)),
            )
            await session.execute(
                text("select public.complete_outbox_job(:job, :lease)"),
                {"job": job_id, "lease": lease_token},
            )
            await session.commit()
            delivered += 1
        except ApiError as error:
            await session.rollback()
            await session.execute(
                text("select public.fail_outbox_job(:job, :lease, :code, 60)"),
                {"job": job_id, "lease": lease_token, "code": error.code},
            )
            await session.commit()
        except Exception:
            logger.exception("outbox_delivery_failed", job_id=str(job_id))
            await session.rollback()
            await session.execute(
                text("select public.fail_outbox_job(:job, :lease, 'DELIVERY_ERROR', 60)"),
                {"job": job_id, "lease": lease_token},
            )
            await session.commit()
    return delivered
