"""
FastAPI layer for the Banking Agent.

Exposes:
  * ``GET  /healthz``            — Railway / load-balancer health probe.
  * ``POST /api/chat``           — Run one planner→executor→aggregate turn.
  * ``GET  /``                   — Serves the conversational web UI from ``src/server/static/``.

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

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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


@app.get("/healthz/redis")
def healthz_redis() -> dict[str, Any]:
    """
    Readiness probe specifically for conversation memory. Returns one of:
      - ``{"status": "ok",       "host", "port", "latency_ms", "message_keys", "summary_keys"}``
          Redis is reachable and we can count existing memory keys.
      - ``{"status": "unconfigured", "reason": "REDIS_HOST/REDIS_PORT not set"}``
          No env vars → chat runs, but without conversation memory.
      - ``{"status": "error",    "host", "port", "reason": ...}``
          Env vars are set but the ping / auth failed.
    """
    # Accept both underscored and Railway-plugin names (REDISHOST/REDISPORT/REDISPASSWORD).
    host = os.environ.get("REDIS_HOST") or os.environ.get("REDISHOST") or ""
    port = os.environ.get("REDIS_PORT") or os.environ.get("REDISPORT") or ""
    password = os.environ.get("REDIS_PASSWORD") or os.environ.get("REDISPASSWORD") or None
    if not host or not port:
        return {
            "status": "unconfigured",
            "reason": "Neither REDIS_HOST/REDIS_PORT nor REDISHOST/REDISPORT are set; chat runs without memory.",
        }

    t0 = time.perf_counter()
    try:
        import redis  # lazy import; redis-py is already a requirement
        client = redis.Redis(
            host=host,
            port=int(port),
            db=0,
            password=password,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        pong = client.ping()
        if not pong:
            raise RuntimeError("PING returned false")
        # Count existing memory keys so the user can confirm the *correct* Redis
        # instance is being used (not some other random one).
        message_keys = len(list(client.scan_iter(match="message_store:*", count=500)))
        summary_keys = len(list(client.scan_iter(match="conversation_summary:*", count=500)))
        return {
            "status": "ok",
            "host": host,
            "port": port,
            "password_set": bool(password),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "message_keys": message_keys,
            "summary_keys": summary_keys,
        }
    except Exception as exc:
        logger.warning("healthz_redis: connect failed: %s", exc)
        return {
            "status": "error",
            "host": host,
            "port": port,
            "password_set": bool(password),
            "reason": f"{type(exc).__name__}: {exc}",
        }


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


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """
    SSE variant of ``/api/chat``. Emits ``status`` / ``plan`` / ``step_done`` / ``final``
    events as the runtime graph advances so the UI can show live progress instead of
    a silent spinner. Each SSE data frame is a single JSON object.
    """
    trace_id = uuid.uuid4().hex[:12]
    extra = {"trace_id": trace_id}
    t0 = time.perf_counter()
    logger.info(
        "chat_stream: received message len=%s customer=%s session=%s",
        len(req.message),
        req.customer_id or "-",
        req.session_id or "-",
        extra=extra,
    )

    def _sse(event: dict) -> str:
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    def event_iter():
        yield _sse({"type": "trace", "trace_id": trace_id})
        try:
            from src.run import run_task_stream  # lazy import
            for ev in run_task_stream(
                user_input=req.message,
                customer_id_number=req.customer_id,
                session_id=req.session_id,
            ):
                yield _sse(ev)
        except Exception as exc:
            logger.exception("chat_stream: generator raised", extra=extra)
            yield _sse({
                "type": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            })
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info("chat_stream: done in %sms", latency_ms, extra=extra)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx / Railway edge)
            "Connection": "keep-alive",
        },
    )


# Static UI last so API routes above take precedence.
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
else:
    logger.warning("static dir not found at %s; web UI unavailable", _STATIC_DIR, extra={"trace_id": "-"})


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("src.server.app:app", host="0.0.0.0", port=port, reload=False)
