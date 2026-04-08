from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from histserv.dashboard.histogram_json import histogram_summary, histogram_to_plot_json
from histserv.service import Histogrammer

# Interval constants (seconds)
_STATS_INTERVAL = 1.0
_HIST_LIST_INTERVAL = 2.0
_PUSH_LOOP_INTERVAL = 0.25  # how often the push loop wakes up


@dataclass(eq=False)  # identity-based equality so instances are hashable in sets
class _ClientState:
    """Per-connection subscription state."""

    websocket: WebSocket
    # Streams the client wants: "stats" and/or "hist_list"
    streams: set[str] = field(default_factory=set)
    # hist_id -> rate_limit_hz (0 means use default 1 Hz)
    hist_subscriptions: dict[str, float] = field(default_factory=dict)
    # timestamps of last push, per stream / hist_id
    last_stream_push: dict[str, float] = field(default_factory=dict)
    last_hist_push: dict[str, float] = field(default_factory=dict)
    # last version (ms timestamp) sent per hist_id, to skip redundant pushes
    last_hist_version: dict[str, int] = field(default_factory=dict)


def _envelope(msg_type: str, payload: dict) -> dict:
    return {"type": msg_type, "ts": time.time(), "payload": payload}


def create_app(
    histogrammer: Histogrammer, *, static_dir: Path | None = None
) -> FastAPI:
    """Create the FastAPI observability app.

    Args:
        histogrammer: The live Histogrammer instance to observe.
        static_dir: If provided, serve built frontend assets from this directory.
    """
    # All connected WS clients
    _clients: set[_ClientState] = set()

    @contextlib.asynccontextmanager
    async def _lifespan(app: FastAPI):  # noqa: ARG001
        asyncio.create_task(_push_loop(), name="dashboard_push_loop")
        yield

    app = FastAPI(title="histserv dashboard", lifespan=_lifespan)

    # ------------------------------------------------------------------ #
    # REST endpoint: one-shot histogram snapshot                           #
    # ------------------------------------------------------------------ #

    @app.get("/api/histograms/{hist_id}")
    async def get_histogram(hist_id: str, token: str | None = None) -> JSONResponse:
        entry = histogrammer._entries.get(hist_id)
        if entry is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if entry.token is not None and entry.token != token:
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            data = await asyncio.to_thread(histogram_to_plot_json, hist_id, entry)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        return JSONResponse(data)

    # ------------------------------------------------------------------ #
    # WebSocket endpoint                                                    #
    # ------------------------------------------------------------------ #

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        state = _ClientState(websocket=websocket)
        _clients.add(state)
        try:
            while True:
                msg = await websocket.receive_json()
                await _handle_client_message(state, msg, histogrammer)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            _clients.discard(state)

    # ------------------------------------------------------------------ #
    # Background push loop (started by lifespan)                           #
    # ------------------------------------------------------------------ #

    async def _push_loop() -> None:
        while True:
            await asyncio.sleep(_PUSH_LOOP_INTERVAL)
            now = time.time()
            dead: list[_ClientState] = []
            for state in list(_clients):
                try:
                    await _push_to_client(state, now, histogrammer)
                except Exception:
                    dead.append(state)
            for state in dead:
                _clients.discard(state)

    # ------------------------------------------------------------------ #
    # Optional static file serving (production mode)                       #
    # ------------------------------------------------------------------ #

    if static_dir is not None and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


async def _handle_client_message(
    state: _ClientState, msg: dict, histogrammer: Histogrammer
) -> None:
    """Route an incoming client message to the appropriate handler."""
    msg_type = msg.get("type")
    payload = msg.get("payload", {})

    if msg_type == "subscribe":
        streams = payload.get("streams", [])
        for s in streams:
            if s in ("stats", "hist_list"):
                state.streams.add(s)
        # Immediately send current data for newly subscribed streams
        now = time.time()
        if "stats" in streams:
            await _send_stats(state, histogrammer)
            state.last_stream_push["stats"] = now
        if "hist_list" in streams:
            await _send_hist_list(state, histogrammer)
            state.last_stream_push["hist_list"] = now

    elif msg_type == "unsubscribe":
        streams = payload.get("streams", [])
        for s in streams:
            state.streams.discard(s)

    elif msg_type == "subscribe_hist":
        hist_id = payload.get("hist_id")
        if hist_id:
            rate_hz = float(payload.get("rate_limit_hz", 1.0))
            state.hist_subscriptions[hist_id] = max(0.1, rate_hz)
            # Immediately send the histogram
            await _send_hist_data(state, hist_id, histogrammer)
            state.last_hist_push[hist_id] = time.time()

    elif msg_type == "unsubscribe_hist":
        hist_id = payload.get("hist_id")
        if hist_id:
            state.hist_subscriptions.pop(hist_id, None)
            state.last_hist_push.pop(hist_id, None)
            state.last_hist_version.pop(hist_id, None)

    elif msg_type == "get_hist":
        hist_id = payload.get("hist_id")
        if hist_id:
            await _send_hist_data(state, hist_id, histogrammer)


async def _push_to_client(
    state: _ClientState, now: float, histogrammer: Histogrammer
) -> None:
    """Evaluate what to push to a single client based on subscriptions and rate limits."""
    # Stats stream (~1s interval)
    if "stats" in state.streams:
        last = state.last_stream_push.get("stats", 0.0)
        if now - last >= _STATS_INTERVAL:
            await _send_stats(state, histogrammer)
            state.last_stream_push["stats"] = now

    # Hist list stream (~2s interval)
    if "hist_list" in state.streams:
        last = state.last_stream_push.get("hist_list", 0.0)
        if now - last >= _HIST_LIST_INTERVAL:
            await _send_hist_list(state, histogrammer)
            state.last_stream_push["hist_list"] = now

    # Per-histogram subscriptions with rate limiting
    for hist_id, rate_hz in list(state.hist_subscriptions.items()):
        min_interval = 1.0 / rate_hz
        last = state.last_hist_push.get(hist_id, 0.0)
        if now - last < min_interval:
            continue

        entry = histogrammer._entries.get(hist_id)
        if entry is None:
            # Histogram was deleted; notify client and clean up
            await state.websocket.send_json(
                _envelope(
                    "error",
                    {
                        "message": f"histogram {hist_id} no longer exists",
                        "code": "NOT_FOUND",
                    },
                )
            )
            state.hist_subscriptions.pop(hist_id, None)
            continue

        # Skip if data hasn't changed since last send
        version = int(entry.last_access.timestamp() * 1000)
        if state.last_hist_version.get(hist_id) == version:
            continue

        await _send_hist_data(state, hist_id, histogrammer)
        state.last_hist_push[hist_id] = now


async def _send_stats(state: _ClientState, histogrammer: Histogrammer) -> None:
    stats = histogrammer._compute_stats(token=None)
    await state.websocket.send_json(
        _envelope(
            "stats",
            {
                "histogram_count": stats.histogram_count,
                "histogram_bytes": stats.histogram_bytes,
                "active_rpcs": stats.active_rpcs,
                "version": stats.version,
                "uptime_seconds": stats.uptime_seconds,
                "cpu_user": stats.user_cpu_seconds,
                "cpu_system": stats.system_cpu_seconds,
                "rpc_calls_total": stats.rpc_calls_total,
                "observed_at": stats.observed_at.timestamp(),
            },
        )
    )


async def _send_hist_list(state: _ClientState, histogrammer: Histogrammer) -> None:
    items = [
        histogram_summary(hist_id, entry)
        for hist_id, entry in histogrammer._entries.items()
    ]
    await state.websocket.send_json(_envelope("hist_list", {"items": items}))


async def _send_hist_data(
    state: _ClientState, hist_id: str, histogrammer: Histogrammer
) -> None:
    entry = histogrammer._entries.get(hist_id)
    if entry is None:
        await state.websocket.send_json(
            _envelope(
                "error",
                {"message": f"histogram {hist_id} not found", "code": "NOT_FOUND"},
            )
        )
        return
    try:
        data = await asyncio.to_thread(histogram_to_plot_json, hist_id, entry)
    except Exception as exc:
        await state.websocket.send_json(
            _envelope("error", {"message": str(exc), "code": "INTERNAL"})
        )
        return
    await state.websocket.send_json(_envelope("hist_data", data))
    state.last_hist_version[hist_id] = data["version"]
