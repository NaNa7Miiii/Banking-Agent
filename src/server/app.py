"""
FastAPI layer for the Banking Agent.

Exposes:
  * ``GET  /healthz``            — Railway / load-balancer health probe.
  * ``POST /api/chat``           — Run one planner→executor→aggregate turn.
  * ``GET  /``                   — Serves ``src/server/static/index.html`` (demo UI).

Design notes:
  * The runtime graph is **not** constructed at import time. We build it lazily on
    the first request so that (a) the Docker image can build without secrets,
    (b) ``/healthz`` stays fast, (c) module-import failures don't crash the server.
  * ``run_task`` returns a dict-ish result; we pick a small, stable subset for the
    wire format so the HTML/JS client doesn't depend on internal state shape.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from src.utils.env import load_env

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s trace=%(trace_id)s %(message)s",
)


class _TraceFilter(logging.Filter):
    """Inject a default ``trace_id`` into every log record so the format string never breaks."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return True


for _h in logging.getLogger().handlers:
    _h.addFilter(_TraceFilter())


_STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(..., min_length=1, max_length=4000)
    customer_id: str = ""
    session_id: str = ""


class ChatResponse(BaseModel):
    trace_id: str
    final_answer: str | None = None
    plan: dict[str, Any] | None = None
    step_results: dict[str, Any] | None = None
    latency_ms: int
    error: str | None = None


app = FastAPI(
    title="Banking Agent API",
    version="0.1.0",
    description="Modular monolith: planner + executor + sub-agents behind one HTTP surface.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    """Load .env early so child imports see the right values, but don't eagerly build the graph."""
    load_env()
    logger.info("startup: env loaded; runtime graph will be built lazily on first /api/chat call", extra={"trace_id": "-"})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe. Deliberately does **not** touch the DB / OpenAI / Pinecone
    so Railway can mark the pod healthy before cold-start warm-up finishes."""
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    trace_id = uuid.uuid4().hex[:12]
    extra = {"trace_id": trace_id}
    t0 = time.perf_counter()
    logger.info("chat: received message len=%s customer=%s session=%s",
                len(req.message), req.customer_id or "-", req.session_id or "-", extra=extra)
    try:
        from src.run import run_task  # lazy import: keep /healthz free of heavy deps
        result = run_task(
            user_input=req.message,
            customer_id_number=req.customer_id,
            session_id=req.session_id,
        )
    except Exception as exc:
        logger.exception("chat: run_task raised", extra=extra)
        return JSONResponse(
            status_code=500,
            content=ChatResponse(
                trace_id=trace_id,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            ).model_dump(),
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("chat: done in %sms", latency_ms, extra=extra)
    return ChatResponse(
        trace_id=trace_id,
        final_answer=result.get("final_answer"),
        plan=result.get("plan"),
        step_results=result.get("step_results"),
        latency_ms=latency_ms,
    )


# Static UI last so API routes above take precedence.
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
else:
    logger.warning("static dir not found at %s; demo UI unavailable", _STATIC_DIR, extra={"trace_id": "-"})


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("src.server.app:app", host="0.0.0.0", port=port, reload=False)
