"""Optional OpenTelemetry traces. Export stays disabled until an OTLP endpoint is configured."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

_EVENT_ATTRIBUTES = {
    "tool", "origin", "duration_ms", "status", "error_code", "caller_turn_id", "generation_id",
    "playback_segment_id", "operation_id", "queue_depth", "queued_ms", "audio_ms", "filler_played",
    "first_audio_latency_ms", "tts_first_audio_ms", "playback_duration_ms", "operation_type",
    "operation_status", "approval_candidate",
    "caller_item_id", "assistant_item_id", "response_id", "provider_tool_call_id",
    "tool_invocation_id", "query_id", "proposal_id", "durable_operation_id",
    "message_source_id", "failure_type", "failure_reason",
}


def configure() -> Any | None:
    """Create one batched OTLP exporter only when an endpoint is explicitly supplied."""
    endpoint = (
        os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    )
    if not endpoint or os.getenv("OTEL_TRACES_EXPORTER", "otlp").lower() == "none":
        logger.info("opentelemetry_tracing_disabled")
        return None

    exporter_kind = os.getenv("OTEL_TRACES_EXPORTER", "otlp").lower()
    if exporter_kind != "otlp":
        logger.error("opentelemetry_exporter_not_supported", extra={"exporter": exporter_kind})
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({
            "service.name": os.getenv("OTEL_SERVICE_NAME", "ai-receptionist-api"),
            "service.version": "0.1.0",
        })
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(timeout=5)
        provider.add_span_processor(BatchSpanProcessor(
            exporter, max_queue_size=2048, max_export_batch_size=512,
        ))
        trace.set_tracer_provider(provider)
        logger.info(
            "opentelemetry_tracing_configured",
            extra={"service_name": resource.attributes.get("service.name")},
        )
        return provider
    except Exception as error:
        logger.error("opentelemetry_setup_failed", extra={"error_type": type(error).__name__})
        return None


def shutdown(provider: Any | None) -> None:
    if provider is None:
        return
    try:
        provider.force_flush(timeout_millis=3000)
        provider.shutdown()
    except Exception as error:
        logger.error("opentelemetry_shutdown_failed", extra={"error_type": type(error).__name__})


def start_voice_call(engine: str) -> Any:
    from opentelemetry import trace

    return trace.get_tracer("ai_receptionist.voice").start_as_current_span(
        "voice.call", attributes={"voice.provider": "voicelink", "voice.engine": engine}
    )


def current_trace_id() -> str | None:
    from opentelemetry import trace

    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid else None


def finish_voice_call(status: str) -> None:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.set_attribute("voice.call.status", status.lower())
    if status != "ENDED":
        # Avoid exporting provider exception messages, which can contain user data.
        span.set_status(Status(StatusCode.ERROR, description="voice call interrupted"))


def add_voice_event(kind: str, stage: str, fields: dict[str, Any]) -> None:
    from opentelemetry import trace

    span = trace.get_current_span()
    if not span.is_recording():
        return
    attributes: dict[str, str | int | float | bool] = {
        "voice.event": kind[:80], "voice.stage": stage[:40],
    }
    candidates = dict(fields)
    if isinstance(candidates.get("details"), dict):
        candidates.update(candidates["details"])
    for key, value in candidates.items():
        if key not in _EVENT_ATTRIBUTES:
            continue
        if isinstance(value, str):
            attributes[f"voice.{key}"] = value[:100]
        elif isinstance(value, (int, float, bool)):
            attributes[f"voice.{key}"] = value
    span.add_event("voice.event", attributes=attributes)


@contextmanager
def span_scope(name: str, attributes: dict[str, str | int | float | bool]) -> Iterator[Any]:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    with trace.get_tracer("ai_receptionist").start_as_current_span(
        name, attributes=attributes
    ) as span:
        try:
            yield span
        except BaseException as error:
            # Record the exception class only; exception text/stack may contain clinical data.
            span.set_attribute("error.type", type(error).__name__[:100])
            span.set_status(Status(StatusCode.ERROR, description="operation failed"))
            raise
