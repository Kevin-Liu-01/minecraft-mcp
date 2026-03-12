from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class BlueprintBlock(BaseModel):
    x: int
    y: int
    z: int
    block: str


class Blueprint(BaseModel):
    name: str
    description: str
    blocks: list[BlueprintBlock] = Field(default_factory=list)
    width: int = 0
    length: int = 0
    height: int = 0
    material: str = "cobblestone"


def _gen_house(
    ox: int, oy: int, oz: int, w: int, l: int, h: int, mat: str, door_mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    roof_y = oy + h - 1

    for x in range(w):
        for z in range(l):
            blocks.append(BlueprintBlock(x=ox + x, y=oy, z=oz + z, block=mat))
            blocks.append(BlueprintBlock(x=ox + x, y=roof_y, z=oz + z, block=mat))

    for y in range(1, h - 1):
        for x in range(w):
            blocks.append(BlueprintBlock(x=ox + x, y=oy + y, z=oz, block=mat))
            blocks.append(BlueprintBlock(x=ox + x, y=oy + y, z=oz + l - 1, block=mat))
        for z in range(1, l - 1):
            blocks.append(BlueprintBlock(x=ox, y=oy + y, z=oz + z, block=mat))
            blocks.append(BlueprintBlock(x=ox + w - 1, y=oy + y, z=oz + z, block=mat))

    door_x = ox + w // 2
    door_z = oz
    blocks = [b for b in blocks if not (b.x == door_x and b.z == door_z and b.y in (oy + 1, oy + 2))]

    return blocks


def _gen_tower(
    ox: int, oy: int, oz: int, radius: int, h: int, mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    for y in range(h):
        for x in range(-radius, radius + 1):
            for z in range(-radius, radius + 1):
                dist_sq = x * x + z * z
                if dist_sq <= radius * radius and (dist_sq >= (radius - 1) ** 2 or y == 0 or y == h - 1):
                    blocks.append(BlueprintBlock(x=ox + x, y=oy + y, z=oz + z, block=mat))
    return blocks


def _gen_wall(
    ox: int, oy: int, oz: int, w: int, h: int, mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    for x in range(w):
        for y in range(h):
            blocks.append(BlueprintBlock(x=ox + x, y=oy + y, z=oz, block=mat))
    return blocks


def _gen_bridge(
    ox: int, oy: int, oz: int, w: int, l: int, mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    for z in range(l):
        for x in range(w):
            blocks.append(BlueprintBlock(x=ox + x, y=oy, z=oz + z, block=mat))
        blocks.append(BlueprintBlock(x=ox - 1, y=oy + 1, z=oz + z, block=mat))
        blocks.append(BlueprintBlock(x=ox + w, y=oy + 1, z=oz + z, block=mat))
    return blocks


def _gen_platform(
    ox: int, oy: int, oz: int, w: int, l: int, mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    for x in range(w):
        for z in range(l):
            blocks.append(BlueprintBlock(x=ox + x, y=oy, z=oz + z, block=mat))
    return blocks


def _gen_stairs(
    ox: int, oy: int, oz: int, h: int, w: int, mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    for step in range(h):
        for x in range(w):
            blocks.append(BlueprintBlock(x=ox + x, y=oy + step, z=oz + step, block=mat))
    return blocks


def _gen_fence(
    ox: int, oy: int, oz: int, w: int, l: int, mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    for x in range(w):
        blocks.append(BlueprintBlock(x=ox + x, y=oy, z=oz, block=mat))
        blocks.append(BlueprintBlock(x=ox + x, y=oy, z=oz + l - 1, block=mat))
    for z in range(1, l - 1):
        blocks.append(BlueprintBlock(x=ox, y=oy, z=oz + z, block=mat))
        blocks.append(BlueprintBlock(x=ox + w - 1, y=oy, z=oz + z, block=mat))
    return blocks


def _gen_pool(
    ox: int, oy: int, oz: int, w: int, l: int, depth: int, mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    for y in range(depth):
        for x in range(w):
            blocks.append(BlueprintBlock(x=ox + x, y=oy - y, z=oz, block=mat))
            blocks.append(BlueprintBlock(x=ox + x, y=oy - y, z=oz + l - 1, block=mat))
        for z in range(1, l - 1):
            blocks.append(BlueprintBlock(x=ox, y=oy - y, z=oz + z, block=mat))
            blocks.append(BlueprintBlock(x=ox + w - 1, y=oy - y, z=oz + z, block=mat))
    for x in range(w):
        for z in range(l):
            blocks.append(BlueprintBlock(x=ox + x, y=oy - depth, z=oz + z, block=mat))
    return blocks


def _gen_farm(
    ox: int, oy: int, oz: int, w: int, l: int, mat: str
) -> list[BlueprintBlock]:
    blocks: list[BlueprintBlock] = []
    for x in range(w):
        for z in range(l):
            blocks.append(BlueprintBlock(x=ox + x, y=oy, z=oz + z, block=mat))
    for x in range(w):
        blocks.append(BlueprintBlock(x=ox + x, y=oy + 1, z=oz - 1, block="oak_fence"))
        blocks.append(BlueprintBlock(x=ox + x, y=oy + 1, z=oz + l, block="oak_fence"))
    for z in range(l):
        blocks.append(BlueprintBlock(x=ox - 1, y=oy + 1, z=oz + z, block="oak_fence"))
        blocks.append(BlueprintBlock(x=ox + w, y=oy + 1, z=oz + z, block="oak_fence"))
    return blocks


def _gen_pillar(
    ox: int, oy: int, oz: int, h: int, mat: str
) -> list[BlueprintBlock]:
    return [BlueprintBlock(x=ox, y=oy + y, z=oz, block=mat) for y in range(h)]


_PARSEABLE_DIMS = re.compile(r"(\d+)\s*[xX×]\s*(\d+)(?:\s*[xX×]\s*(\d+))?")


def _parse_dimensions(text: str) -> tuple[int, int, int]:
    match = _PARSEABLE_DIMS.search(text)
    if match:
        w = int(match.group(1))
        l = int(match.group(2))
        h = int(match.group(3)) if match.group(3) else 4
        return max(w, 1), max(l, 1), max(h, 1)
    return 5, 5, 4


def _extract_number(text: str, default: int) -> int:
    nums = re.findall(r"\d+", text)
    return int(nums[0]) if nums else default


def generate_blueprint(
    description: str,
    origin_x: int = 0,
    origin_y: int = 64,
    origin_z: int = 0,
    material: str = "cobblestone",
) -> Blueprint:
    desc_lower = description.lower()
    w, l, h = _parse_dimensions(description)

    if any(kw in desc_lower for kw in ("house", "cabin", "home", "cottage")):
        blocks = _gen_house(origin_x, origin_y, origin_z, w, l, h, material, "air")
        return Blueprint(name="house", description=description, blocks=blocks, width=w, length=l, height=h, material=material)

    if any(kw in desc_lower for kw in ("tower", "turret", "spire")):
        radius = max(w, l) // 2 or 2
        blocks = _gen_tower(origin_x, origin_y, origin_z, radius, h, material)
        return Blueprint(name="tower", description=description, blocks=blocks, width=radius * 2, length=radius * 2, height=h, material=material)

    if "wall" in desc_lower:
        blocks = _gen_wall(origin_x, origin_y, origin_z, w, h, material)
        return Blueprint(name="wall", description=description, blocks=blocks, width=w, length=1, height=h, material=material)

    if "bridge" in desc_lower:
        blocks = _gen_bridge(origin_x, origin_y, origin_z, w, l, material)
        return Blueprint(name="bridge", description=description, blocks=blocks, width=w, length=l, height=2, material=material)

    if any(kw in desc_lower for kw in ("platform", "floor", "pad")):
        blocks = _gen_platform(origin_x, origin_y, origin_z, w, l, material)
        return Blueprint(name="platform", description=description, blocks=blocks, width=w, length=l, height=1, material=material)

    if any(kw in desc_lower for kw in ("stair", "steps", "ladder")):
        blocks = _gen_stairs(origin_x, origin_y, origin_z, h, w, material)
        return Blueprint(name="stairs", description=description, blocks=blocks, width=w, length=h, height=h, material=material)

    if any(kw in desc_lower for kw in ("fence", "perimeter", "enclosure")):
        blocks = _gen_fence(origin_x, origin_y, origin_z, w, l, material)
        return Blueprint(name="fence", description=description, blocks=blocks, width=w, length=l, height=1, material=material)

    if "pool" in desc_lower:
        depth = _extract_number(desc_lower.split("pool")[0], 3)
        blocks = _gen_pool(origin_x, origin_y, origin_z, w, l, depth, material)
        return Blueprint(name="pool", description=description, blocks=blocks, width=w, length=l, height=depth, material=material)

    if "farm" in desc_lower:
        blocks = _gen_farm(origin_x, origin_y, origin_z, w, l, material)
        return Blueprint(name="farm", description=description, blocks=blocks, width=w, length=l, height=2, material=material)

    if "pillar" in desc_lower:
        blocks = _gen_pillar(origin_x, origin_y, origin_z, h, material)
        return Blueprint(name="pillar", description=description, blocks=blocks, width=1, length=1, height=h, material=material)

    blocks = _gen_house(origin_x, origin_y, origin_z, w, l, h, material, "air")
    return Blueprint(name="structure", description=description, blocks=blocks, width=w, length=l, height=h, material=material)
