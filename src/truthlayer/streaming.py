"""SSE progress streaming for the verification graph.

Perceived vs actual latency: streaming does not make the pipeline one second
faster — total time is identical. What changes is the wait's *shape*: a
20-second blank spinner feels broken by second eight, while "3 sub-claims
identified → evidence from nasa.gov, wikipedia.org → verdict forming" is a
progress narrative the user can watch. Perceived latency is a function of
feedback frequency, not wall-clock time.

SSE vs the alternatives: a regular HTTP response is one buffered body —
nothing renders until everything is done. WebSockets give bidirectional
messaging (chat, games) at the cost of a stateful upgrade handshake and
fussier proxies. Server-Sent Events are one-directional server→client push
over plain HTTP: exactly the shape of "server narrates progress, client
listens", with built-in reconnection semantics and none of the upgrade
ceremony. The graph already exposes per-node updates via LangGraph's
stream(), so each node completion becomes one SSE event.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from truthlayer.graph import TruthLayerState, get_graph, result_payload

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict[str, Any]) -> str:
    """Format one SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _domains(urls: list[str]) -> list[str]:
    seen: list[str] = []
    for url in urls:
        domain = urlparse(url).netloc.removeprefix("www.")
        if domain and domain not in seen:
            seen.append(domain)
    return seen


def stream_verification(claim: str) -> Iterator[str]:
    """Run the graph and yield SSE frames as each node completes.

    The graph is synchronous, so it runs on a worker thread feeding a queue;
    this generator drains the queue and yields formatted SSE frames. The
    final frame is either `result` (the full verdict payload) or `error`.
    """
    frames: queue.Queue[str | None] = queue.Queue()

    def run() -> None:
        try:
            initial: TruthLayerState = {
                "claim": claim,
                "retry_count": 0,
                "llm_calls_used": 0,
                "errors": [],
                "ingested_urls": [],
                "chunks_stored": 0,
            }
            state: dict[str, Any] = dict(initial)
            for update in get_graph().stream(initial, stream_mode="updates"):
                for node, node_state in update.items():
                    if node_state:
                        state.update(node_state)
                    frames.put(_progress_frame(node, state))
            if state.get("verdict") is None:
                frames.put(_sse("error", {"message": "Pipeline produced no verdict."}))
            else:
                frames.put(
                    _sse("result", {**result_payload(claim, state), "served_from_cache": False})
                )
        except Exception:
            logger.exception("Streaming verification failed")
            frames.put(_sse("error", {"message": "Verification failed — please try again."}))
        finally:
            frames.put(None)  # sentinel: stream complete

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    while True:
        frame = frames.get()
        if frame is None:
            break
        yield frame


def _progress_frame(node: str, state: dict[str, Any]) -> str:
    """Translate a completed graph node into a user-meaningful SSE event."""
    if node == "decompose":
        return _sse("sub_claims", {"sub_claims": state.get("sub_claims", [])})
    if node == "search_and_embed":
        return _sse(
            "evidence",
            {
                "chunks_stored": state.get("chunks_stored", 0),
                "source_domains": _domains(state.get("ingested_urls", [])),
            },
        )
    if node == "retrieve":
        return _sse("retrieved", {"evidence_count": len(state.get("evidence", []))})
    if node == "judge":
        return _sse("judging", {"confidence": state.get("confidence", 0.0)})
    if node == "broaden":
        return _sse(
            "retrying",
            {"retry": state.get("retry_count", 0), "queries": state.get("search_queries", [])},
        )
    return _sse("stage", {"stage": node})
