from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Position(BaseModel):
    x: int
    y: int
    z: int


class InventoryEntry(BaseModel):
    item: str
    count: int = Field(ge=0)


class EntitySnapshot(BaseModel):
    name: str
    kind: str | None = None
    x: int | None = None
    y: int | None = None
    z: int | None = None


class ChatEntry(BaseModel):
    sender: str
    message: str
    type: str = "system"
    timestamp: str


class BotStatus(BaseModel):
    connected: bool
    mode: str | None = None
    username: str | None = None
    host: str | None = None
    port: int | None = None
    position: Position | None = None
    health: float | None = None
    food: float | None = None
    inventory: list[InventoryEntry] = Field(default_factory=list)
    entities: list[EntitySnapshot] = Field(default_factory=list)
    chat_backlog: int = 0


class WorldSnapshot(BaseModel):
    radius: int
    position: Position | None = None
    visible_blocks: list[dict[str, Any]] = Field(default_factory=list)
    nearby_entities: list[dict[str, Any]] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)


class GoalRecommendation(BaseModel):
    phase: str
    reason: str
    checklist: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)

