from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.knowledge import SessionLog

router = APIRouter(prefix="/status", tags=["Status"])


async def build_daily_status(user_id: str, window_hours: int = 24) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SessionLog)
            .where(SessionLog.user_id == user_id, SessionLog.created_at >= since)
            .order_by(SessionLog.created_at.desc())
            .limit(50)
        )
        rows = result.scalars().all()

    if not rows:
        return {
            "user_id": user_id,
            "window_hours": window_hours,
            "attempts": 0,
            "average_score_delta": 0.0,
            "latest_topic": None,
            "latest_verdict": None,
            "message": "No sessions yet in the selected time window.",
        }

    deltas = [r.score_delta for r in rows if r.score_delta is not None]
    avg_delta = round(sum(deltas) / len(deltas), 3) if deltas else 0.0
    latest = rows[0]
    latest_verdict = None
    if latest.evaluation and isinstance(latest.evaluation, dict):
        latest_verdict = latest.evaluation.get("verdict")

    return {
        "user_id": user_id,
        "window_hours": window_hours,
        "attempts": len(rows),
        "average_score_delta": avg_delta,
        "latest_topic": latest.topic,
        "latest_verdict": latest_verdict,
        "last_activity_at": latest.created_at.isoformat() if latest.created_at else None,
    }


@router.get("/daily/{user_id}")
async def daily_status(user_id: str, hours: int = 24):
    if hours <= 0 or hours > 24 * 14:
        raise HTTPException(status_code=400, detail="hours must be between 1 and 336")
    return await build_daily_status(user_id, window_hours=hours)
