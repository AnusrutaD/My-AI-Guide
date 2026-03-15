"""
Execute Router — Code execution via Piston API.

Endpoints:
  POST /execute  → Run code with stdin, returns stdout/stderr
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/execute", tags=["Execute"])

PISTON_URL = "https://emkc.org/api/v2/piston/execute"

# Map frontend language ids to Piston language names
LANGUAGE_MAP = {
    "python": "python",
    "javascript": "javascript",
    "java": "java",
    "cpp": "c++",
    "c": "c",
    "go": "go",
    "rust": "rust",
    "typescript": "typescript",
    "ruby": "ruby",
    "csharp": "csharp",
    "kotlin": "kotlin",
    "php": "php",
    "swift": "swift",
}


class ExecuteRequest(BaseModel):
    language: str = Field(..., description="Language id: python, javascript, java, cpp, etc.")
    code: str = Field(..., description="Source code to execute")
    stdin: str = Field("", description="Standard input for the program")


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    code: int | None
    signal: str | None
    run_error: str | None = None


@router.post("/run", response_model=ExecuteResponse)
async def run_code(body: ExecuteRequest) -> ExecuteResponse:
    """
    Execute code via Piston API. Uses stdin for input, returns stdout/stderr.
    """
    lang = body.language.lower().strip()
    piston_lang = LANGUAGE_MAP.get(lang, lang)

    payload: dict[str, Any] = {
        "language": piston_lang,
        "version": "*",
        "files": [{"content": body.code}],
        "stdin": body.stdin,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(PISTON_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("[Execute] Piston API error: %s", e.response.text)
        raise HTTPException(status_code=502, detail="Code execution service unavailable") from e
    except Exception as e:
        logger.exception("[Execute] Failed to call Piston")
        raise HTTPException(status_code=502, detail=str(e)) from e

    run = data.get("run") or {}
    return ExecuteResponse(
        stdout=run.get("stdout", ""),
        stderr=run.get("stderr", ""),
        code=run.get("code"),
        signal=run.get("signal"),
        run_error=data.get("message"),
    )
