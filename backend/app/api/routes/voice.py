import asyncio
import hashlib
import hmac
from contextlib import suppress
from typing import Any
from urllib.parse import parse_qsl
from xml.etree.ElementTree import Element, SubElement, tostring

import structlog
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.voice.gateway import TwilioVoiceGateway, VoiceProtocolError
from app.voice.presentation import presentation_scope
from app.voice.security import (
    create_stream_binding,
    valid_twilio_signature,
)
from app.voice.voicelink_gateway import VoiceLinkVoiceGateway
from app.voice.voicelink_realtime_gateway import VoiceLinkRealtimeGateway

router = APIRouter()
logger = structlog.get_logger()


async def _signed_twilio_parameters(request: Request, path: str) -> dict[str, str] | None:
    settings = get_settings()
    body = await request.body()
    parameters = dict(parse_qsl(body.decode("utf-8"), keep_blank_values=True))
    public_url = f"{str(settings.public_backend_url).rstrip('/')}{path}"
    if request.url.query:
        public_url += f"?{request.url.query}"
    if not valid_twilio_signature(
        public_url,
        parameters,
        request.headers.get("X-Twilio-Signature"),
        settings.twilio_auth_token,
    ):
        return None
    return parameters


@router.post("/twilio/personal-voice")
async def personal_twilio_voice(request: Request) -> Response:
    from app.personal_agent.callbacks import bound_attempt
    from app.personal_agent.config import get_personal_settings
    from app.personal_agent.twilio_callbacks import configured

    settings, config = get_settings(), get_personal_settings()
    parameters = await _signed_twilio_parameters(request, "/v1/twilio/personal-voice")
    token = request.query_params.get("binding", "")
    attempt = bound_attempt(settings.verification_code_pepper or "", {"friday_binding": token})
    if not (
        parameters
        and configured(settings)
        and config.enabled
        and config.owner_id
        and attempt
        and parameters.get("Direction", "").startswith("outbound")
        and parameters.get("To") == config.registered_phone
        and parameters.get("From") == settings.twilio_phone_number
        and parameters.get("AccountSid") == settings.twilio_account_sid
    ):
        return Response("Invalid personal callback route.", status_code=403)
    response = Element("Response")
    stream = SubElement(
        SubElement(response, "Connect"),
        "Stream",
        url=str(settings.public_backend_url)
        .rstrip("/")
        .replace("https://", "wss://")
        .replace("http://", "ws://")
        + "/v1/twilio/personal-media",
    )
    SubElement(stream, "Parameter", name="friday_binding", value=token)
    call_binding = hmac.new(
        (settings.verification_code_pepper or "").encode(),
        f"friday:{parameters.get('CallSid', '')}:{token}".encode(),
        hashlib.sha256,
    ).hexdigest()
    SubElement(stream, "Parameter", name="call_binding", value=call_binding)
    SubElement(response, "Say").text = "Friday's connection has ended. Goodbye."
    return Response(tostring(response, encoding="unicode"), media_type="application/xml")


@router.post("/twilio/personal-status")
async def personal_twilio_status(request: Request) -> Response:
    from app.personal_agent.callbacks import process_callback_event

    settings = get_settings()
    parameters = await _signed_twilio_parameters(request, "/v1/twilio/personal-status")
    from app.personal_agent.config import get_personal_settings

    if (
        not parameters
        or parameters.get("AccountSid") != settings.twilio_account_sid
        or parameters.get("To") != get_personal_settings().registered_phone
        or parameters.get("From") != settings.twilio_phone_number
    ):
        return Response(status_code=403)
    status = parameters.get("CallStatus", "")
    if status not in {
        "initiated",
        "ringing",
        "in-progress",
        "completed",
        "busy",
        "no-answer",
        "failed",
        "canceled",
    }:
        return Response(status_code=400)
    kind = {
        "initiated": "call.initiated",
        "ringing": "call.initiated",
        "in-progress": "call.answered",
    }.get(status, "call.completed")
    await process_callback_event(
        settings.model_copy(update={"voicelink_phone_number": settings.twilio_phone_number}),
        {
            "event": kind,
            "callId": parameters.get("CallSid"),
            "fromNumber": parameters.get("From"),
            "toNumber": parameters.get("To"),
            "callStatus": status,
            "custom_parameters": {"friday_binding": request.query_params.get("binding", "")},
        },
    )
    return Response(status_code=204)


@router.websocket("/twilio/personal-media")
async def personal_twilio_media(websocket: WebSocket) -> None:
    from app.personal_agent.callbacks import bound_attempt
    from app.personal_agent.config import get_personal_settings
    from app.personal_agent.routing import select_callback_call
    from app.personal_agent.twilio_callbacks import configured
    from app.personal_agent.voice.twilio import PersonalTwilioGateway

    settings, config = get_settings(), get_personal_settings()
    url = str(settings.public_backend_url).rstrip("/") + "/v1/twilio/personal-media"
    stream_url = url.replace("https://", "wss://").replace("http://", "ws://")
    signature = websocket.headers.get("X-Twilio-Signature")
    if not (
        configured(settings)
        and config.enabled
        and any(
            valid_twilio_signature(candidate, {}, signature, settings.twilio_auth_token)
            for candidate in (url, url + "/", stream_url, stream_url + "/")
        )
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async with asyncio.timeout(15):
            message = await websocket.receive_json()
            if message.get("event") == "connected":
                message = await websocket.receive_json()
        start = message.get("start", {})
        if not isinstance(start, dict):
            raise VoiceProtocolError("Missing Twilio personal start.")
        media = start.get("mediaFormat", {})
        attempt = bound_attempt(
            settings.verification_code_pepper or "", start.get("customParameters")
        )
        custom = start.get("customParameters", {})
        if not isinstance(custom, dict):
            raise VoiceProtocolError("Missing Twilio callback binding.")
        signed_call = f"friday:{start.get('callSid', '')}:{custom.get('friday_binding', '')}"
        expected = hmac.new(
            (settings.verification_code_pepper or "").encode(), signed_call.encode(), hashlib.sha256
        ).hexdigest()
        if not (
            message.get("event") == "start"
            and attempt
            and hmac.compare_digest(str(custom.get("call_binding", "")), expected)
            and start.get("accountSid") == settings.twilio_account_sid
            and media.get("encoding") == "audio/x-mulaw"
            and media.get("sampleRate") == 8000
            and media.get("channels") == 1
            and start.get("callSid")
            and start.get("streamSid")
        ):
            raise VoiceProtocolError("Invalid Twilio personal start.")
        context = {
            "caller": config.registered_phone or "",
            "called": settings.twilio_phone_number or "",
            "call_sid": str(start["callSid"]),
            "stream_sid": str(start["streamSid"]),
            "direction": "outbound",
            "attempt_id": str(attempt),
        }
        selected = await select_callback_call(settings, config, context, provider="twilio")
        if selected is None:
            raise VoiceProtocolError("Personal callback is unavailable.")
        await PersonalTwilioGateway(settings, config, context, *selected).run(websocket)
    except (VoiceProtocolError, WebSocketDisconnect, TimeoutError):
        with suppress(RuntimeError):
            await websocket.close(code=1008)


@router.post("/twilio/voice")
async def inbound_voice(request: Request) -> Response:
    settings = get_settings()
    if not settings.twilio_voice_configured or not settings.verification_code_pepper:
        return Response("Voice integration is not configured.", status_code=503)
    parameters = await _signed_twilio_parameters(request, "/v1/twilio/voice")
    if parameters is None:
        return Response("Invalid Twilio signature.", status_code=403)
    call_sid = parameters.get("CallSid", "")
    from_number = parameters.get("From", "")
    to_number = parameters.get("To", "")
    direction = parameters.get("Direction", "")
    if direction.startswith("outbound"):
        caller = to_number
        called = from_number
    else:
        caller = from_number
        called = to_number
    if not call_sid or not caller or called != settings.twilio_phone_number:
        return Response("Invalid call route.", status_code=400)
    assert settings.voice_organization_id is not None
    assert settings.voice_actor_id is not None
    binding = create_stream_binding(
        call_sid=call_sid,
        caller=caller,
        called=called,
        organization_id=settings.voice_organization_id,
        actor_id=settings.voice_actor_id,
        secret=settings.verification_code_pepper,
    )

    response = Element("Response")
    greeting = SubElement(response, "Say", language="en-IN", voice="Polly.Aditi")
    greeting.text = (
        "Hello. You are speaking with the A I receptionist for Geeta Medicine. "
        "You may speak in English or Hindi. How may I help you?"
    )
    connect = SubElement(response, "Connect")
    stream = SubElement(
        connect,
        "Stream",
        url=settings.public_websocket_url or "",
        statusCallback=(f"{str(settings.public_backend_url).rstrip('/')}/v1/twilio/stream-status"),
    )
    SubElement(stream, "Parameter", name="binding", value=binding)
    fallback = SubElement(response, "Say", language="en-IN", voice="Polly.Aditi")
    fallback.text = "The A I receptionist is unavailable. Please call the clinic again shortly."
    return Response(tostring(response, encoding="unicode"), media_type="application/xml")


@router.post("/twilio/stream-status")
async def stream_status(request: Request) -> Response:
    parameters = await _signed_twilio_parameters(request, "/v1/twilio/stream-status")
    if parameters is None:
        return Response("Invalid Twilio signature.", status_code=403)
    logger.info(
        "twilio_stream_status",
        call_sid=parameters.get("CallSid"),
        stream_sid=parameters.get("StreamSid"),
        stream_event=parameters.get("StreamEvent"),
        stream_error=parameters.get("StreamError"),
    )
    return Response(status_code=204)


@router.websocket("/twilio/media")
async def voice_media(websocket: WebSocket) -> None:
    settings = get_settings()
    public_url = settings.public_websocket_url or ""
    signature = websocket.headers.get("X-Twilio-Signature")
    valid_signature = valid_twilio_signature(
        public_url, {}, signature, settings.twilio_auth_token
    ) or valid_twilio_signature(
        f"{public_url.rstrip('/')}/", {}, signature, settings.twilio_auth_token
    )
    if not settings.twilio_voice_configured or not valid_signature:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        await TwilioVoiceGateway(settings).run(websocket)
    except (VoiceProtocolError, WebSocketDisconnect):
        await websocket.close(code=1008)


def _valid_voicelink_token(provided: str | None, expected: str | None) -> bool:
    return bool(provided and expected and hmac.compare_digest(provided, expected))


def _capture_connection_attempt(status: str) -> None:
    from app.observability.capture import capture

    settings = get_settings()
    if capture and settings.voice_organization_id:
        capture.attempt(str(settings.voice_organization_id), status)


@router.websocket("/voicelink/media")
async def voicelink_media(websocket: WebSocket) -> None:
    settings = get_settings()
    if not settings.voicelink_voice_configured:
        _capture_connection_attempt("CONFIGURATION_INCOMPLETE")
        logger.error("voicelink_connection_rejected", reason="configuration_incomplete")
        await websocket.close(code=1008)
        return
    if not _valid_voicelink_token(
        websocket.query_params.get("token"), settings.voicelink_stream_secret
    ):
        _capture_connection_attempt("INVALID_TOKEN")
        logger.warning("voicelink_connection_rejected", reason="invalid_stream_token")
        await websocket.close(code=1008)
        return
    await websocket.accept()
    _capture_connection_attempt("ACCEPTED")
    logger.info("voicelink_connection_accepted", engine=settings.voice_engine)
    try:
        gateway = (
            VoiceLinkRealtimeGateway(settings)
            if settings.voice_engine == "realtime" or settings.voice_realtime_canary_callers
            else VoiceLinkVoiceGateway(settings)
        )
        with presentation_scope(settings):
            from app.personal_agent.config import get_personal_settings

            try:
                personal = get_personal_settings()
            except Exception as error:
                logger.warning("personal_configuration_failed", error_type=type(error).__name__)
                personal = None
            if personal and personal.enabled and personal.owner_id:
                from app.personal_agent.routing import (
                    select_callback_call,
                    select_personal_call,
                    validate_start,
                )
                from app.personal_agent.voice.voicelink import (
                    PersonalVoiceLinkGateway,
                    receive_personal_voicelink_input,
                    stream_startup_audio,
                )

                # Authenticate the stream above, then read/validate start exactly once.
                async with asyncio.timeout(10):
                    for _ in range(8):
                        initial = await websocket.receive_json()
                        if initial.get("event") == "connected":
                            continue
                        if initial.get("event") != "start":
                            raise VoiceProtocolError("Expected VoiceLink stream start.")
                        break
                    else:
                        raise VoiceProtocolError("Missing VoiceLink stream start.")
                context = validate_start(initial, settings)
                startup_stop = asyncio.Event()
                startup_lock = asyncio.Lock()
                greeting_started = asyncio.Event()
                incoming_events: asyncio.Queue[dict[str, Any] | Exception] | None = None
                receiver_task = None
                if context["direction"] == "outbound":
                    incoming_events = asyncio.Queue(maxsize=1024)
                    receiver_task = asyncio.create_task(
                        receive_personal_voicelink_input(
                            websocket,
                            incoming_events,
                            startup_stop,
                            context["call_sid"],
                        )
                    )
                startup_task = (
                    asyncio.create_task(
                        stream_startup_audio(
                            websocket,
                            context["stream_sid"],
                            startup_stop,
                            startup_lock,
                            greeting_started,
                        )
                    )
                    if context["direction"] == "outbound"
                    else None
                )
                try:
                    try:
                        async with asyncio.timeout(10):
                            selected = await (
                                select_callback_call(settings, personal, context)
                                if context["direction"] == "outbound"
                                else select_personal_call(settings, personal, context)
                            )
                    except TimeoutError:
                        logger.warning("personal_route_lookup_timed_out")
                        selected = None
                    if selected:
                        await PersonalVoiceLinkGateway(
                            settings,
                            personal,
                            context,
                            selected[0],
                            selected[1],
                            startup_silence_stop=startup_stop,
                            send_lock=startup_lock,
                            opening_greeting_started=greeting_started,
                            incoming_events=incoming_events,
                        ).run(websocket)
                    else:
                        if context["direction"] == "outbound":
                            raise VoiceProtocolError("Unrecognized Friday callback.")
                        await gateway.run(websocket, initial_message=initial)
                finally:
                    startup_stop.set()
                    if startup_task is not None:
                        startup_task.cancel()
                        await asyncio.gather(startup_task, return_exceptions=True)
                    if receiver_task is not None:
                        receiver_task.cancel()
                        await asyncio.gather(receiver_task, return_exceptions=True)
            else:
                await gateway.run(websocket)
    except VoiceProtocolError as error:
        logger.warning("voicelink_protocol_error", error=str(error))
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=1008)
    except WebSocketDisconnect as error:
        logger.info("voicelink_websocket_disconnected", close_code=error.code)
    except Exception as error:
        _capture_connection_attempt("FAILED")
        logger.exception("voicelink_gateway_failed", error_type=type(error).__name__)
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=1011)


@router.post("/voicelink/events")
async def voicelink_events(request: Request) -> Response:
    settings = get_settings()
    if not _valid_voicelink_token(
        request.query_params.get("token"), settings.voicelink_stream_secret
    ):
        return Response("Invalid VoiceLink token.", status_code=403)
    payload = await request.json()
    logger.info(
        "voicelink_call_event",
        event_type=payload.get("event"),
        call_id=payload.get("callId"),
        direction=payload.get("direction"),
        call_status=payload.get("callStatus"),
        duration=payload.get("duration"),
    )
    from app.personal_agent.callbacks import process_callback_event

    await process_callback_event(settings, payload)
    return Response(status_code=204)
