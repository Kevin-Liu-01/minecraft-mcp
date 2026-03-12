from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("MINECRAFT_MCP_DATA_DIR", ".minecraft_mcp_data"))

SKILLS_FILE = DATA_DIR / "skills.json"
MEMORY_FILE = DATA_DIR / "world_memory.json"
SESSION_FILE = DATA_DIR / "session_history.json"
PLANS_FILE = DATA_DIR / "plans.json"

GAME_MODE_SURVIVAL = "survival"
GAME_MODE_CREATIVE = "creative"

WOOD_BLOCKS = frozenset({
    "oak_log", "birch_log", "spruce_log", "jungle_log",
    "acacia_log", "dark_oak_log", "mangrove_log", "cherry_log",
})
STONE_BLOCKS = frozenset({"cobblestone", "stone", "deepslate", "cobbled_deepslate"})
ORE_BLOCKS = frozenset({
    "coal_ore", "iron_ore", "gold_ore", "diamond_ore",
    "lapis_ore", "redstone_ore", "emerald_ore",
    "copper_ore", "deepslate_iron_ore", "deepslate_gold_ore",
    "deepslate_diamond_ore", "deepslate_coal_ore",
})
PLANK_BLOCKS = frozenset({
    "oak_planks", "birch_planks", "spruce_planks", "jungle_planks",
    "acacia_planks", "dark_oak_planks", "mangrove_planks", "cherry_planks",
})

TOOL_TIERS = ["wooden", "stone", "iron", "golden", "diamond", "netherite"]
TOOL_TYPES = ["pickaxe", "axe", "shovel", "sword", "hoe"]

FOOD_ITEMS = frozenset({
    "bread", "cooked_beef", "cooked_porkchop", "cooked_chicken",
    "cooked_mutton", "cooked_salmon", "cooked_cod", "baked_potato",
    "golden_apple", "apple", "melon_slice", "sweet_berries",
    "cooked_rabbit", "mushroom_stew", "beetroot_soup", "rabbit_stew",
})

SMELTABLE_ITEMS: dict[str, str] = {
    "raw_iron": "iron_ingot",
    "raw_gold": "gold_ingot",
    "raw_copper": "copper_ingot",
    "iron_ore": "iron_ingot",
    "gold_ore": "gold_ingot",
    "copper_ore": "copper_ingot",
    "sand": "glass",
    "cobblestone": "stone",
    "clay_ball": "brick",
    "netherrack": "nether_brick",
    "wet_sponge": "sponge",
    "beef": "cooked_beef",
    "porkchop": "cooked_porkchop",
    "chicken": "cooked_chicken",
    "mutton": "cooked_mutton",
    "rabbit": "cooked_rabbit",
    "cod": "cooked_cod",
    "salmon": "cooked_salmon",
    "potato": "baked_potato",
    "kelp": "dried_kelp",
}

FUEL_ITEMS: dict[str, int] = {
    "coal": 8,
    "charcoal": 8,
    "oak_log": 1,
    "birch_log": 1,
    "spruce_log": 1,
    "jungle_log": 1,
    "acacia_log": 1,
    "dark_oak_log": 1,
    "oak_planks": 1,
    "birch_planks": 1,
    "spruce_planks": 1,
    "stick": 0,
    "lava_bucket": 100,
    "blaze_rod": 12,
}

BUILDING_MATERIALS = frozenset({
    "cobblestone", "stone", "stone_bricks", "oak_planks", "birch_planks",
    "spruce_planks", "jungle_planks", "acacia_planks", "dark_oak_planks",
    "bricks", "sandstone", "red_sandstone", "quartz_block", "prismarine",
    "deepslate_bricks", "polished_deepslate", "dirt", "glass",
    "oak_log", "birch_log", "spruce_log",
})

MAX_RETRY_ATTEMPTS = 3
RETRY_MOVE_OFFSET = 3
DEFAULT_PATHFIND_TIMEOUT_MS = 30_000

CREATIVE_COMMANDS = frozenset({
    "gamemode", "give", "tp", "teleport", "fill", "setblock",
    "time", "weather", "effect", "enchant", "summon", "kill",
    "clear", "clone", "execute",
})
