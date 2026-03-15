"""
WhatsApp Webhook Router — Twilio integration.

Flow:
  1. Twilio delivers inbound WhatsApp messages to POST /webhook/whatsapp
  2. We parse the From number and Body
  3. Map the WhatsApp number to a user_id (or create one)
  4. Determine current session stage and either:
     a. Start a new session (if none / idle)
     b. Submit a response to be evaluated (if testing)
  5. Send the reply back via Twilio MessagingResponse

Mock mode (no Twilio creds):
  POST /webhook/mock  with JSON body { "from": "+1234567890", "body": "..." }
  Returns the mentor's reply as plain JSON — useful for local testing.
"""

import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.routers.status import build_daily_status
from app.services.clarifier import generate_clarification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])

# In-memory phone → thread_id mapping (replace with Redis/DB in production)
_phone_sessions: dict[str, dict[str, Any]] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_phone(raw: str) -> str:
    """Strip 'whatsapp:' prefix and normalise to E.164."""
    return re.sub(r"[^\d+]", "", raw.replace("whatsapp:", ""))


def _get_or_create_session(phone: str) -> dict[str, Any]:
    if phone not in _phone_sessions:
        _phone_sessions[phone] = {
            "user_id": f"wa_{phone.lstrip('+')}",
            "thread_id": str(uuid.uuid4()),
            "stage": "idle",
        }
    return _phone_sessions[phone]


def _twilio_twiml(message: str) -> Response:
    """Return a minimal TwiML MessagingResponse."""
    # Escape XML special chars
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Truncate to WhatsApp's 4096-char limit
    if len(safe) > 4000:
        safe = safe[:3990] + "\n…[truncated — see full feedback via API]"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{safe}</Message>"
        "</Response>"
    )
    return Response(content=xml, media_type="text/xml")


async def _run_mentor(
    request: Request,
    phone: str,
    user_id: str,
    thread_id: str,
    body: str,
    stage: str,
) -> str:
    """Route to the correct graph action and return the mentor's text reply."""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        return "⚠️ Mentor system is starting up. Try again in a moment."

    config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
    lowered = body.strip().lower()

    if lowered in {"status", "daily", "progress"}:
        status = await build_daily_status(user_id, window_hours=24)
        return (
            "Daily status (last 24h)\n"
            f"- Attempts: {status['attempts']}\n"
            f"- Avg score delta: {status['average_score_delta']:+.3f}\n"
            f"- Latest topic: {status['latest_topic'] or 'N/A'}\n"
            f"- Latest verdict: {status['latest_verdict'] or 'N/A'}\n"
            f"- Last activity: {status.get('last_activity_at') or 'N/A'}\n\n"
            "Reply 'start' for a new challenge."
        )

    from app.graph.state import DEFAULT_STATE

    if stage == "idle" or lowered in ("start", "next", "hello", "hi"):
        initial_state: dict = {
            **DEFAULT_STATE,
            "user_id": user_id,
            "thread_id": thread_id,
            "interview_stage": "idle",
        }
        final_state = await graph.ainvoke(initial_state, config=config)
        _phone_sessions[phone]["stage"] = "testing"
        return final_state.get("question_text", "Error generating question — please try again.")

    elif stage == "testing":
        if lowered.startswith("clarify:") or lowered.startswith("ask:"):
            snapshot = await graph.aget_state(config)
            values = snapshot.values or {}
            question_text = values.get("question_text", "")
            question_json = values.get("current_question", {})
            user_query = body.split(":", 1)[1].strip() if ":" in body else body.strip()
            clarification = await generate_clarification(
                question_text=question_text,
                question_json=question_json,
                candidate_question=user_query,
            )
            return (
                f"{clarification}\n\n"
                "Send `clarify: <your question>` for more requirement clarifications, "
                "or send your full solution when ready."
            )

        # User is submitting their answer
        await graph.aupdate_state(
            config,
            {"user_response": body, "interview_stage": "review"},
        )
        final_state = await graph.ainvoke(None, config=config)
        _phone_sessions[phone]["stage"] = "idle"
        eval_result = final_state.get("evaluation_result", {})
        feedback = eval_result.get("feedback", "Evaluation complete.")
        verdict = eval_result.get("verdict", "?")
        delta = eval_result.get("score_delta", 0.0)
        return f"**{verdict}** (score Δ {delta:+.2f})\n\n{feedback}\n\nReply *next* for your next challenge."

    return "Reply *start* to begin your daily challenge."


# ── Twilio Webhook ─────────────────────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
):
    """
    Twilio inbound WhatsApp webhook.
    Twilio expects a TwiML XML response.
    """
    from app.config import get_settings
    settings = get_settings()

    # Optional: validate Twilio signature in production
    # from twilio.request_validator import RequestValidator
    # validator = RequestValidator(settings.twilio_auth_token)
    # if not validator.validate(str(request.url), await request.form(), request.headers.get("X-Twilio-Signature", "")):
    #     raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    phone = _normalise_phone(From)
    session = _get_or_create_session(phone)
    user_id = session["user_id"]
    thread_id = session["thread_id"]
    stage = session.get("stage", "idle")

    logger.info("[Webhook] Inbound from=%s stage=%s body_len=%d", phone, stage, len(Body))

    try:
        reply = await _run_mentor(request, phone, user_id, thread_id, Body, stage)
    except Exception as exc:
        logger.exception("[Webhook] Mentor error for phone=%s", phone)
        reply = f"⚠️ Internal error: {exc}. The team has been notified."

    return _twilio_twiml(reply)


# ── Mock Endpoint (local testing without Twilio) ───────────────────────────────

class MockWebhookRequest(BaseModel):
    from_number: str = Field("+10000000001", alias="from")
    body: str

    class Config:
        populate_by_name = True


@router.post("/mock")
async def mock_whatsapp(payload: MockWebhookRequest, request: Request):
    """
    Simulate a WhatsApp message without Twilio.
    Useful for integration testing the full graph end-to-end.

    Example:
        curl -X POST http://localhost:8000/webhook/mock \\
          -H 'Content-Type: application/json' \\
          -d '{"from": "+10000000001", "body": "start"}'
    """
    phone = _normalise_phone(payload.from_number)
    session = _get_or_create_session(phone)
    user_id = session["user_id"]
    thread_id = session["thread_id"]
    stage = session.get("stage", "idle")

    logger.info("[MockWebhook] from=%s stage=%s", phone, stage)

    try:
        reply = await _run_mentor(request, phone, user_id, thread_id, payload.body, stage)
    except Exception as exc:
        logger.exception("[MockWebhook] Error for phone=%s", phone)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "stage_before": stage,
            "stage_after": _phone_sessions.get(phone, {}).get("stage", "idle"),
            "reply": reply,
        }
    )
