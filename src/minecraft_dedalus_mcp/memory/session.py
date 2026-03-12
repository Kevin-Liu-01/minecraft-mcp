from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..constants import SESSION_FILE


class ActionRecord(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | str | None = None
    success: bool = True
    error: str | None = None
    timestamp: float = Field(default_factory=time.time)
    duration_ms: float = 0


class SessionHistory:
    def __init__(self, path: Path | None = None, max_records: int = 500) -> None:
        self._path = path or SESSION_FILE
        self._records: list[ActionRecord] = []
        self._max_records = max_records
        self._load()

    def _ensure_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw = json.loads(self._path.read_text())
        self._records = [ActionRecord.model_validate(r) for r in raw]

    def _save(self) -> None:
        self._ensure_dir()
        data = [r.model_dump() for r in self._records[-self._max_records :]]
        self._path.write_text(json.dumps(data, indent=2))

    def record_action(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any = None,
        success: bool = True,
        error: str | None = None,
        duration_ms: float = 0,
    ) -> ActionRecord:
        record = ActionRecord(
            tool_name=tool_name,
            args=args,
            result=result if isinstance(result, (dict, str, type(None))) else str(result),
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records :]
        self._save()
        return record

    def get_recent(self, limit: int = 20) -> list[ActionRecord]:
        return self._records[-limit:]

    def get_failures(self, limit: int = 10) -> list[ActionRecord]:
        failures = [r for r in self._records if not r.success]
        return failures[-limit:]

    def get_by_tool(self, tool_name: str, limit: int = 10) -> list[ActionRecord]:
        matches = [r for r in self._records if r.tool_name == tool_name]
        return matches[-limit:]

    def clear(self) -> None:
        self._records.clear()
        self._save()

    def summarize(self) -> dict[str, Any]:
        if not self._records:
            return {"total": 0, "successes": 0, "failures": 0, "tools_used": []}

        tool_counts: dict[str, int] = {}
        successes = 0
        failures = 0
        for r in self._records:
            tool_counts[r.tool_name] = tool_counts.get(r.tool_name, 0) + 1
            if r.success:
                successes += 1
            else:
                failures += 1

        top_tools = sorted(tool_counts.items(), key=lambda p: p[1], reverse=True)[:10]
        return {
            "total": len(self._records),
            "successes": successes,
            "failures": failures,
            "tools_used": [{"tool": t, "count": c} for t, c in top_tools],
            "recent_failures": [
                {"tool": r.tool_name, "error": r.error}
                for r in self.get_failures(5)
            ],
        }
