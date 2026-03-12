from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..constants import SKILLS_FILE


class ToolCall(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class SkillEntry(BaseModel):
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    tool_sequence: list[ToolCall] = Field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    created_at: float = Field(default_factory=time.time)
    last_used: float | None = None


class SkillStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or SKILLS_FILE
        self._skills: dict[str, SkillEntry] = {}
        self._load()

    def _ensure_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            for entry in raw:
                skill = SkillEntry.model_validate(entry)
                self._skills[skill.name] = skill

    def _save(self) -> None:
        self._ensure_dir()
        data = [s.model_dump() for s in self._skills.values()]
        self._path.write_text(json.dumps(data, indent=2))

    def add_skill(
        self,
        name: str,
        description: str,
        tool_sequence: list[dict[str, Any]],
        tags: list[str] | None = None,
    ) -> SkillEntry:
        calls = [ToolCall.model_validate(tc) for tc in tool_sequence]
        entry = SkillEntry(
            name=name,
            description=description,
            tags=tags or [],
            tool_sequence=calls,
        )
        self._skills[name] = entry
        self._save()
        return entry

    def get_skill(self, name: str) -> SkillEntry | None:
        return self._skills.get(name)

    def find_skills(self, query: str, limit: int = 5) -> list[SkillEntry]:
        query_lower = query.lower()
        tokens = query_lower.split()

        scored: list[tuple[float, SkillEntry]] = []
        for skill in self._skills.values():
            searchable = f"{skill.name} {skill.description} {' '.join(skill.tags)}".lower()
            score = sum(1 for t in tokens if t in searchable)
            if score > 0:
                score += skill.success_count * 0.1
                scored.append((score, skill))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [s for _, s in scored[:limit]]

    def record_success(self, name: str) -> None:
        skill = self._skills.get(name)
        if skill:
            skill.success_count += 1
            skill.last_used = time.time()
            self._save()

    def record_failure(self, name: str) -> None:
        skill = self._skills.get(name)
        if skill:
            skill.failure_count += 1
            skill.last_used = time.time()
            self._save()

    def remove_skill(self, name: str) -> bool:
        if name in self._skills:
            del self._skills[name]
            self._save()
            return True
        return False

    def list_skills(self) -> list[SkillEntry]:
        return sorted(self._skills.values(), key=lambda s: s.success_count, reverse=True)

    def to_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "tags": s.tags,
                "steps": len(s.tool_sequence),
                "successes": s.success_count,
            }
            for s in self.list_skills()
        ]
