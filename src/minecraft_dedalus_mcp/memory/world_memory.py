from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..constants import MEMORY_FILE


class LocationEntry(BaseModel):
    name: str
    x: int
    y: int
    z: int
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    discovered_at: float = Field(default_factory=time.time)


class ResourceDeposit(BaseModel):
    block_name: str
    x: int
    y: int
    z: int
    estimated_count: int = 1
    last_seen: float = Field(default_factory=time.time)


class StructureRecord(BaseModel):
    name: str
    origin_x: int
    origin_y: int
    origin_z: int
    width: int = 0
    length: int = 0
    height: int = 0
    block_count: int = 0
    built_at: float = Field(default_factory=time.time)


class WorldMemory:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or MEMORY_FILE
        self._locations: list[LocationEntry] = []
        self._resources: list[ResourceDeposit] = []
        self._structures: list[StructureRecord] = []
        self._load()

    def _ensure_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw = json.loads(self._path.read_text())
        self._locations = [LocationEntry.model_validate(e) for e in raw.get("locations", [])]
        self._resources = [ResourceDeposit.model_validate(e) for e in raw.get("resources", [])]
        self._structures = [StructureRecord.model_validate(e) for e in raw.get("structures", [])]

    def _save(self) -> None:
        self._ensure_dir()
        data = {
            "locations": [e.model_dump() for e in self._locations],
            "resources": [e.model_dump() for e in self._resources],
            "structures": [e.model_dump() for e in self._structures],
        }
        self._path.write_text(json.dumps(data, indent=2))

    def save_location(
        self,
        name: str,
        x: int,
        y: int,
        z: int,
        tags: list[str] | None = None,
        notes: str = "",
    ) -> LocationEntry:
        for loc in self._locations:
            if loc.name == name:
                loc.x, loc.y, loc.z = x, y, z
                loc.tags = tags or loc.tags
                loc.notes = notes or loc.notes
                self._save()
                return loc
        entry = LocationEntry(name=name, x=x, y=y, z=z, tags=tags or [], notes=notes)
        self._locations.append(entry)
        self._save()
        return entry

    def get_locations(self, tag: str | None = None) -> list[LocationEntry]:
        if tag is None:
            return list(self._locations)
        return [loc for loc in self._locations if tag in loc.tags]

    def find_nearest_location(
        self, x: int, y: int, z: int, tag: str | None = None
    ) -> LocationEntry | None:
        candidates = self.get_locations(tag)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda loc: math.sqrt((loc.x - x) ** 2 + (loc.y - y) ** 2 + (loc.z - z) ** 2),
        )

    def save_resource(
        self,
        block_name: str,
        x: int,
        y: int,
        z: int,
        estimated_count: int = 1,
    ) -> ResourceDeposit:
        for res in self._resources:
            if res.block_name == block_name and abs(res.x - x) < 16 and abs(res.z - z) < 16:
                res.x, res.y, res.z = x, y, z
                res.estimated_count = max(res.estimated_count, estimated_count)
                res.last_seen = time.time()
                self._save()
                return res
        entry = ResourceDeposit(
            block_name=block_name, x=x, y=y, z=z, estimated_count=estimated_count
        )
        self._resources.append(entry)
        self._save()
        return entry

    def find_resource(self, block_name: str) -> list[ResourceDeposit]:
        return [r for r in self._resources if r.block_name == block_name]

    def find_nearest_resource(
        self, block_name: str, x: int, y: int, z: int
    ) -> ResourceDeposit | None:
        candidates = self.find_resource(block_name)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda r: math.sqrt((r.x - x) ** 2 + (r.y - y) ** 2 + (r.z - z) ** 2),
        )

    def save_structure(
        self,
        name: str,
        origin_x: int,
        origin_y: int,
        origin_z: int,
        width: int = 0,
        length: int = 0,
        height: int = 0,
        block_count: int = 0,
    ) -> StructureRecord:
        entry = StructureRecord(
            name=name,
            origin_x=origin_x,
            origin_y=origin_y,
            origin_z=origin_z,
            width=width,
            length=length,
            height=height,
            block_count=block_count,
        )
        self._structures.append(entry)
        self._save()
        return entry

    def get_structures(self) -> list[StructureRecord]:
        return list(self._structures)

    def to_summary(self) -> dict[str, Any]:
        return {
            "locations": len(self._locations),
            "resources": len(self._resources),
            "structures": len(self._structures),
            "location_names": [loc.name for loc in self._locations[:20]],
            "resource_types": list({r.block_name for r in self._resources}),
            "structure_names": [s.name for s in self._structures[:20]],
        }
