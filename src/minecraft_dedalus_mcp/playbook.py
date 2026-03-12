from __future__ import annotations

from collections import Counter

from .models import BotStatus, GoalRecommendation


def _inventory_counts(status: BotStatus) -> Counter[str]:
    counts: Counter[str] = Counter()
    for entry in status.inventory:
        counts[entry.item] += entry.count
    return counts


def recommend_goal(status: BotStatus, objective: str = "beat-minecraft") -> GoalRecommendation:
    if not status.connected:
        return GoalRecommendation(
            phase="connect",
            reason="The bot is not connected to any Minecraft world yet.",
            checklist=[
                "Start the bridge in real or simulated mode.",
                "Call join_game with the LAN host, port, and bot username.",
            ],
            suggested_tools=["join_game", "get_bot_status"],
        )

    inventory = _inventory_counts(status)
    objective = objective.strip().lower()

    if objective in {"build-house", "build_hut", "build"}:
        if inventory["oak_log"] < 4 and inventory["oak_planks"] < 16:
            return GoalRecommendation(
                phase="gather-wood",
                reason="A small starter build still needs more wood-derived material.",
                checklist=[
                    "Mine at least 4 oak_log.",
                    "Craft at least 16 oak_planks.",
                    "Keep extra dirt or cobblestone for temporary scaffolding.",
                ],
                suggested_tools=["mine_resource", "craft_items", "inspect_world"],
            )
        return GoalRecommendation(
            phase="build-starter-hut",
            reason="You have enough early material to place a starter structure.",
            checklist=[
                "Move to a flat position.",
                "Call build_structure with preset='hut'.",
                "Inspect the build area after placement.",
            ],
            suggested_tools=["go_to_known_location", "build_structure", "inspect_world"],
        )

    if inventory["eye_of_ender"] >= 12:
        return GoalRecommendation(
            phase="stronghold-and-dragon",
            reason="The essential materials for portal activation are already present.",
            checklist=[
                "Use eyes to trace the stronghold.",
                "Stock blocks, food, bow, and beds or arrows.",
                "Enter the End and prepare for crystal cleanup and dragon damage phases.",
            ],
            suggested_tools=["go_to_known_location", "inspect_world", "send_chat"],
        )

    if inventory["blaze_rod"] >= 6 and inventory["ender_pearl"] >= 12:
        return GoalRecommendation(
            phase="eyes-of-ender",
            reason="You already have the late-game ingredients and should convert them into eyes next.",
            checklist=[
                "Craft blaze_powder from blaze_rod.",
                "Craft eye_of_ender until at least 12 exist.",
            ],
            suggested_tools=["craft_items"],
        )

    if inventory["oak_log"] + inventory["oak_planks"] < 4:
        return GoalRecommendation(
            phase="wood-age",
            reason="The bot still needs basic wood for the first tool and crafting table tier.",
            checklist=[
                "Mine at least 4 oak_log.",
                "Craft oak_planks.",
                "Craft a crafting_table and stick.",
            ],
            suggested_tools=["mine_resource", "craft_items", "inspect_world"],
        )

    if inventory["wooden_pickaxe"] < 1 and inventory["stone_pickaxe"] < 1 and inventory["iron_pickaxe"] < 1:
        return GoalRecommendation(
            phase="first-pickaxe",
            reason="No pickaxe is available, so progression is still blocked on the first crafted tool.",
            checklist=[
                "Craft stick if missing.",
                "Craft wooden_pickaxe.",
                "Use it to reach cobblestone quickly.",
            ],
            suggested_tools=["craft_items", "mine_resource"],
        )

    if inventory["cobblestone"] < 11 and inventory["stone_pickaxe"] < 1 and inventory["iron_pickaxe"] < 1:
        return GoalRecommendation(
            phase="stone-upgrade",
            reason="Stone tools and a furnace are the next stable upgrade path.",
            checklist=[
                "Mine at least 11 cobblestone.",
                "Craft stone_pickaxe.",
                "Craft furnace.",
            ],
            suggested_tools=["mine_resource", "craft_items"],
        )

    if inventory["iron_pickaxe"] < 1:
        iron_total = inventory["raw_iron"] + inventory["iron_ingot"]
        if iron_total < 3:
            return GoalRecommendation(
                phase="iron-age",
                reason="An iron pickaxe unlocks reliable nether and late-game progression.",
                checklist=[
                    "Mine raw_iron.",
                    "Smelt or otherwise convert it to iron_ingot.",
                    "Craft iron_pickaxe.",
                ],
                suggested_tools=["mine_resource", "smelt_item", "craft_items", "inspect_world"],
            )
        return GoalRecommendation(
            phase="craft-iron-pickaxe",
            reason="Enough iron is present to craft the key survival upgrade.",
            checklist=[
                "Craft iron_pickaxe.",
                "Optionally craft shield and bucket next.",
            ],
            suggested_tools=["craft_items"],
        )

    if inventory["blaze_rod"] < 6:
        return GoalRecommendation(
            phase="nether-prep",
            reason="Blaze rods are the first hard gate for eye_of_ender production.",
            checklist=[
                "Prepare food, armor, and blocks for a nether trip.",
                "Travel to the fortress area.",
                "Fight blazes until at least 6 blaze_rod are secured.",
            ],
            suggested_tools=["inspect_world", "go_to_known_location", "attack_entity"],
        )

    if inventory["ender_pearl"] < 12:
        return GoalRecommendation(
            phase="ender-pearls",
            reason="The run still lacks enough pearls for stronghold location and portal activation.",
            checklist=[
                "Locate endermen or a pearl trading loop.",
                "Collect until at least 12 ender_pearl.",
            ],
            suggested_tools=["inspect_world", "attack_entity"],
        )

    if inventory["eye_of_ender"] < 12:
        return GoalRecommendation(
            phase="eyes-of-ender",
            reason="You have the ingredients for final navigation but still need the combined eyes.",
            checklist=[
                "Craft blaze_powder from blaze_rod.",
                "Craft eye_of_ender until at least 12 exist.",
            ],
            suggested_tools=["craft_items"],
        )

    return GoalRecommendation(
        phase="stronghold-and-dragon",
        reason="The essential materials for portal activation are present.",
        checklist=[
            "Use eyes to trace the stronghold.",
            "Stock blocks, food, bow, and beds or arrows.",
            "Enter the End and prepare for crystal cleanup and dragon damage phases.",
        ],
        suggested_tools=["go_to_known_location", "inspect_world", "send_chat"],
    )
