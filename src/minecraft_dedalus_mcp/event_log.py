"""Shared structured event log for agent activity.

Events are stored in-memory and optionally flushed to a JSON-lines file.
The dashboard reads from this log to display real-time agent activity.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class Event:
    ts: float
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


_MAX_EVENTS = 500
_lock = threading.Lock()
_events: list[Event] = []
_log_path: Path | None = None


def configure(path: Path | None = None) -> None:
    global _log_path
    _log_path = path


def emit(kind: str, **data: Any) -> Event:
    ev = Event(ts=time.time(), kind=kind, data=data)
    with _lock:
        _events.append(ev)
        if len(_events) > _MAX_EVENTS:
            del _events[: len(_events) - _MAX_EVENTS]
    if _log_path:
        try:
            _log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(_log_path, "a") as f:
                f.write(json.dumps(asdict(ev), default=str) + "\n")
        except OSError:
            pass
    return ev


def get_events(since: float = 0, limit: int = 200) -> list[dict[str, Any]]:
    with _lock:
        filtered = [asdict(e) for e in _events if e.ts > since]
    return filtered[-limit:]


def clear() -> None:
    with _lock:
        _events.clear()
