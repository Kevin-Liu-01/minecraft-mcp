from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..constants import PLANS_FILE


class PlanStep(BaseModel):
    step_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    result: dict[str, Any] | str | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    status: str = "pending"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


_GOAL_DECOMPOSITIONS: dict[str, list[dict[str, Any]]] = {
    "gather_wood": [
        {"description": "Scan for nearby trees", "tool_name": "inspect_world", "tool_args": {"radius": 32}},
        {"description": "Mine oak logs", "tool_name": "mine_resource", "tool_args": {"name": "oak_log", "count": 10}},
        {"description": "Craft planks from logs", "tool_name": "craft_items", "tool_args": {"item": "oak_planks", "count": 4}},
    ],
    "get_stone_tools": [
        {"description": "Ensure we have wood", "tool_name": "mine_resource", "tool_args": {"name": "oak_log", "count": 4}},
        {"description": "Craft planks", "tool_name": "craft_items", "tool_args": {"item": "oak_planks", "count": 4}},
        {"description": "Craft sticks", "tool_name": "craft_items", "tool_args": {"item": "stick", "count": 4}},
        {"description": "Craft wooden pickaxe", "tool_name": "craft_items", "tool_args": {"item": "wooden_pickaxe", "count": 1}},
        {"description": "Mine cobblestone", "tool_name": "mine_resource", "tool_args": {"name": "cobblestone", "count": 11}},
        {"description": "Craft stone pickaxe", "tool_name": "craft_items", "tool_args": {"item": "stone_pickaxe", "count": 1}},
        {"description": "Craft furnace", "tool_name": "craft_items", "tool_args": {"item": "furnace", "count": 1}},
    ],
    "get_iron_tools": [
        {"description": "Check world for iron ore", "tool_name": "inspect_world", "tool_args": {"radius": 32}},
        {"description": "Mine iron ore", "tool_name": "mine_resource", "tool_args": {"name": "iron_ore", "count": 6}},
        {"description": "Smelt raw iron into ingots", "tool_name": "smelt_item", "tool_args": {"item": "raw_iron", "count": 6}},
        {"description": "Craft iron pickaxe", "tool_name": "craft_items", "tool_args": {"item": "iron_pickaxe", "count": 1}},
        {"description": "Craft iron sword", "tool_name": "craft_items", "tool_args": {"item": "iron_sword", "count": 1}},
    ],
    "build_shelter": [
        {"description": "Gather building materials", "tool_name": "mine_resource", "tool_args": {"name": "oak_log", "count": 16}},
        {"description": "Craft planks for building", "tool_name": "craft_items", "tool_args": {"item": "oak_planks", "count": 16}},
        {"description": "Find flat ground", "tool_name": "inspect_world", "tool_args": {"radius": 16}},
        {"description": "Build a starter hut", "tool_name": "build_structure", "tool_args": {"preset": "hut", "material": "oak_planks", "origin_x": 0, "origin_y": 64, "origin_z": 0, "width": 5, "length": 5, "height": 4}},
    ],
    "hunt_food": [
        {"description": "Look for animals nearby", "tool_name": "inspect_world", "tool_args": {"radius": 32}},
        {"description": "Attack passive mobs for food", "tool_name": "attack_entity", "tool_args": {"name": "cow", "count": 3}},
        {"description": "Collect dropped items", "tool_name": "collect_items", "tool_args": {"radius": 16}},
    ],
    "explore_area": [
        {"description": "Check surroundings", "tool_name": "inspect_world", "tool_args": {"radius": 32}},
        {"description": "Move north to explore", "tool_name": "go_to_known_location", "tool_args": {"x": 0, "y": 64, "z": -50, "range": 2, "timeout_ms": 30000}},
        {"description": "Scan new area", "tool_name": "inspect_world", "tool_args": {"radius": 32}},
    ],
    "prepare_nether": [
        {"description": "Gather obsidian", "tool_name": "mine_resource", "tool_args": {"name": "obsidian", "count": 10}},
        {"description": "Craft flint_and_steel", "tool_name": "craft_items", "tool_args": {"item": "flint_and_steel", "count": 1}},
        {"description": "Stock up on food", "tool_name": "mine_resource", "tool_args": {"name": "oak_log", "count": 8}},
    ],
}


def _match_goal(goal: str) -> str | None:
    goal_lower = goal.lower().replace("-", "_").replace(" ", "_")
    for key in _GOAL_DECOMPOSITIONS:
        if key in goal_lower:
            return key
    keyword_map = {
        "wood": "gather_wood",
        "log": "gather_wood",
        "stone": "get_stone_tools",
        "pickaxe": "get_stone_tools",
        "iron": "get_iron_tools",
        "shelter": "build_shelter",
        "house": "build_shelter",
        "hut": "build_shelter",
        "food": "hunt_food",
        "eat": "hunt_food",
        "hunt": "hunt_food",
        "explore": "explore_area",
        "scout": "explore_area",
        "nether": "prepare_nether",
    }
    for keyword, plan_key in keyword_map.items():
        if keyword in goal_lower:
            return plan_key
    return None


class TaskPlanner:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or PLANS_FILE
        self._plans: dict[str, Plan] = {}
        self._load()

    def _ensure_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw = json.loads(self._path.read_text())
        for entry in raw:
            plan = Plan.model_validate(entry)
            self._plans[plan.plan_id] = plan

    def _save(self) -> None:
        self._ensure_dir()
        data = [p.model_dump() for p in self._plans.values()]
        self._path.write_text(json.dumps(data, indent=2))

    def create_plan(self, goal: str, context: dict[str, Any] | None = None) -> Plan:
        matched = _match_goal(goal)
        if matched and matched in _GOAL_DECOMPOSITIONS:
            steps = [PlanStep(**step_data) for step_data in _GOAL_DECOMPOSITIONS[matched]]
        else:
            steps = [
                PlanStep(
                    description=f"Execute goal: {goal}",
                    tool_name="inspect_world",
                    tool_args={"radius": 32},
                ),
            ]

        plan = Plan(goal=goal, steps=steps, status="pending")
        self._plans[plan.plan_id] = plan
        self._save()
        return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def get_next_step(self, plan_id: str) -> PlanStep | None:
        plan = self._plans.get(plan_id)
        if not plan:
            return None
        for step in plan.steps:
            if step.status == "pending":
                return step
        return None

    def mark_step_started(self, plan_id: str, step_id: str) -> None:
        plan = self._plans.get(plan_id)
        if not plan:
            return
        for step in plan.steps:
            if step.step_id == step_id:
                step.status = "in_progress"
                step.started_at = time.time()
                plan.status = "in_progress"
                plan.updated_at = time.time()
                self._save()
                return

    def mark_step_complete(
        self, plan_id: str, step_id: str, result: Any = None
    ) -> None:
        plan = self._plans.get(plan_id)
        if not plan:
            return
        for step in plan.steps:
            if step.step_id == step_id:
                step.status = "completed"
                step.result = result if isinstance(result, (dict, str, type(None))) else str(result)
                step.completed_at = time.time()
                break
        if all(s.status == "completed" for s in plan.steps):
            plan.status = "completed"
        plan.updated_at = time.time()
        self._save()

    def mark_step_failed(
        self, plan_id: str, step_id: str, error: str
    ) -> None:
        plan = self._plans.get(plan_id)
        if not plan:
            return
        for step in plan.steps:
            if step.step_id == step_id:
                step.status = "failed"
                step.error = error
                step.completed_at = time.time()
                break
        plan.status = "failed"
        plan.updated_at = time.time()
        self._save()

    def list_plans(self, status: str | None = None) -> list[Plan]:
        plans = list(self._plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        return sorted(plans, key=lambda p: p.created_at, reverse=True)

    def to_summary(self, plan_id: str) -> dict[str, Any] | None:
        plan = self._plans.get(plan_id)
        if not plan:
            return None
        completed = sum(1 for s in plan.steps if s.status == "completed")
        failed = sum(1 for s in plan.steps if s.status == "failed")
        return {
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "status": plan.status,
            "total_steps": len(plan.steps),
            "completed": completed,
            "failed": failed,
            "remaining": len(plan.steps) - completed - failed,
            "steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "tool": s.tool_name,
                    "status": s.status,
                }
                for s in plan.steps
            ],
        }
