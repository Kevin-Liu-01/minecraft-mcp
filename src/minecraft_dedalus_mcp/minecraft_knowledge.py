"""Minecraft game knowledge for agent reasoning.

Contains prerequisite chains, tool requirements, crafting recipes, and
progression knowledge that the LLM agent needs to plan multi-step tasks.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Mining tool requirements
# Maps block → minimum tool tier needed. "hand" means breakable by hand.
# ---------------------------------------------------------------------------
MINING_REQUIREMENTS: dict[str, str] = {
    # Hand-breakable
    "dirt": "hand",
    "sand": "hand",
    "gravel": "hand",
    "clay": "hand",
    "soul_sand": "hand",
    "grass_block": "hand",
    "oak_log": "hand",
    "birch_log": "hand",
    "spruce_log": "hand",
    "jungle_log": "hand",
    "acacia_log": "hand",
    "dark_oak_log": "hand",
    "mangrove_log": "hand",
    "cherry_log": "hand",
    "oak_leaves": "hand",
    "crafting_table": "hand",

    # Requires wooden pickaxe or better
    "stone": "wooden_pickaxe",
    "cobblestone": "wooden_pickaxe",
    "sandstone": "wooden_pickaxe",
    "coal_ore": "wooden_pickaxe",
    "copper_ore": "wooden_pickaxe",
    "netherrack": "wooden_pickaxe",
    "furnace": "wooden_pickaxe",

    # Requires stone pickaxe or better
    "iron_ore": "stone_pickaxe",
    "deepslate_iron_ore": "stone_pickaxe",
    "lapis_ore": "stone_pickaxe",
    "copper_ore": "stone_pickaxe",

    # Requires iron pickaxe or better
    "gold_ore": "iron_pickaxe",
    "diamond_ore": "iron_pickaxe",
    "redstone_ore": "iron_pickaxe",
    "emerald_ore": "iron_pickaxe",
    "deepslate_gold_ore": "iron_pickaxe",
    "deepslate_diamond_ore": "iron_pickaxe",
    "deepslate_redstone_ore": "iron_pickaxe",
    "deepslate_emerald_ore": "iron_pickaxe",
    "obsidian": "diamond_pickaxe",

    # Ancient debris (netherite) requires diamond
    "ancient_debris": "diamond_pickaxe",
}

# ---------------------------------------------------------------------------
# Crafting recipes (simplified: item → {ingredient: count})
# Only includes recipes the agent commonly needs for survival progression.
# ---------------------------------------------------------------------------
CRAFTING_RECIPES: dict[str, dict[str, int]] = {
    "oak_planks": {"oak_log": 1},
    "birch_planks": {"birch_log": 1},
    "spruce_planks": {"spruce_log": 1},
    "stick": {"oak_planks": 2},
    "crafting_table": {"oak_planks": 4},
    "chest": {"oak_planks": 8},
    "furnace": {"cobblestone": 8},

    # Wooden tools
    "wooden_pickaxe": {"oak_planks": 3, "stick": 2},
    "wooden_axe": {"oak_planks": 3, "stick": 2},
    "wooden_sword": {"oak_planks": 2, "stick": 1},
    "wooden_shovel": {"oak_planks": 1, "stick": 2},
    "wooden_hoe": {"oak_planks": 2, "stick": 2},

    # Stone tools
    "stone_pickaxe": {"cobblestone": 3, "stick": 2},
    "stone_axe": {"cobblestone": 3, "stick": 2},
    "stone_sword": {"cobblestone": 2, "stick": 1},
    "stone_shovel": {"cobblestone": 1, "stick": 2},

    # Iron tools
    "iron_pickaxe": {"iron_ingot": 3, "stick": 2},
    "iron_axe": {"iron_ingot": 3, "stick": 2},
    "iron_sword": {"iron_ingot": 2, "stick": 1},
    "iron_shovel": {"iron_ingot": 1, "stick": 2},

    # Diamond tools
    "diamond_pickaxe": {"diamond": 3, "stick": 2},
    "diamond_axe": {"diamond": 3, "stick": 2},
    "diamond_sword": {"diamond": 2, "stick": 1},

    # Armor
    "iron_helmet": {"iron_ingot": 5},
    "iron_chestplate": {"iron_ingot": 8},
    "iron_leggings": {"iron_ingot": 7},
    "iron_boots": {"iron_ingot": 4},
    "diamond_helmet": {"diamond": 5},
    "diamond_chestplate": {"diamond": 8},

    # Utility
    "torch": {"coal": 1, "stick": 1},
    "bucket": {"iron_ingot": 3},
    "shield": {"iron_ingot": 1, "oak_planks": 6},
    "bed": {"oak_planks": 3, "white_wool": 3},
    "bread": {"wheat": 3},
    "bowl": {"oak_planks": 3},
    "boat": {"oak_planks": 5},
}

# ---------------------------------------------------------------------------
# Tool tier ordering for comparing tool adequacy
# ---------------------------------------------------------------------------
TOOL_TIER_ORDER = ["hand", "wooden", "stone", "iron", "golden", "diamond", "netherite"]

# ---------------------------------------------------------------------------
# Survival progression stages
# ---------------------------------------------------------------------------
PROGRESSION_STAGES = [
    {
        "name": "Punch a tree",
        "description": "Get logs by punching trees. No tools needed.",
        "goal": "Collect 5+ logs",
        "requires": [],
    },
    {
        "name": "Craft basic tools",
        "description": "Turn logs into planks, planks into sticks, then craft wooden pickaxe + sword.",
        "goal": "Wooden pickaxe + wooden sword",
        "requires": ["5 logs"],
    },
    {
        "name": "Mine stone",
        "description": "Use wooden pickaxe to mine cobblestone (stone drops cobblestone).",
        "goal": "Collect 20+ cobblestone",
        "requires": ["wooden_pickaxe"],
    },
    {
        "name": "Upgrade to stone tools",
        "description": "Craft stone pickaxe, stone sword, stone axe from cobblestone + sticks.",
        "goal": "Stone pickaxe + stone sword",
        "requires": ["cobblestone", "sticks", "crafting_table"],
    },
    {
        "name": "Build shelter + furnace",
        "description": "Place crafting table, craft furnace from 8 cobblestone, build walls/roof.",
        "goal": "Furnace placed, basic shelter built",
        "requires": ["cobblestone", "crafting_table"],
    },
    {
        "name": "Find and smelt iron",
        "description": "Mine iron ore with stone pickaxe (or better), smelt raw_iron in furnace with coal/charcoal fuel.",
        "goal": "Iron ingots",
        "requires": ["stone_pickaxe", "furnace", "fuel (coal or charcoal or logs)"],
    },
    {
        "name": "Iron tools + armor",
        "description": "Craft iron pickaxe, iron sword, iron armor set from iron ingots.",
        "goal": "Iron pickaxe + iron sword + some iron armor",
        "requires": ["iron_ingot", "sticks", "crafting_table"],
    },
    {
        "name": "Find diamonds",
        "description": "Mine at Y=-59 to Y=16 with iron pickaxe. Diamond ore requires iron pickaxe.",
        "goal": "Diamonds",
        "requires": ["iron_pickaxe"],
    },
]


def format_prerequisite_knowledge() -> str:
    """Build the Minecraft prerequisite knowledge section for agent instructions."""
    lines = [
        "## Minecraft prerequisite knowledge — ALWAYS reason about these BEFORE acting",
        "",
        "### CRITICAL: Tool requirements for mining",
        "You CANNOT mine certain blocks without the right tool. Attempting to mine without the correct tool",
        "wastes time and drops nothing. ALWAYS check your inventory for the required tool BEFORE mining.",
        "",
        "| Block | Minimum tool required |",
        "|-------|----------------------|",
        "| Dirt, sand, gravel, logs, leaves | Hand (no tool needed) |",
        "| Stone, cobblestone, coal ore, sandstone, furnace | Wooden pickaxe |",
        "| Iron ore, lapis ore, copper ore | Stone pickaxe |",
        "| Gold ore, diamond ore, redstone ore, emerald ore | Iron pickaxe |",
        "| Obsidian | Diamond pickaxe |",
        "| Ancient debris | Diamond pickaxe |",
        "",
        "### CRITICAL: Crafting dependency chains",
        "Before crafting anything, trace the FULL dependency chain back to raw materials you actually have.",
        "",
        "**Example: Player says 'mine stone' but you have no tools:**",
        "1. Stone requires wooden_pickaxe → need 3 planks + 2 sticks",
        "2. Sticks require planks → need 2 planks (gives 4 sticks)",
        "3. Planks require logs → need 2 logs (gives 8 planks)",
        "4. Logs require: nothing (punch trees)",
        "5. So the FULL chain is: punch trees → craft planks → craft sticks → craft wooden_pickaxe → mine stone",
        "",
        "**Common crafting chains:**",
        "- Wooden pickaxe: logs → planks → sticks + planks → wooden_pickaxe",
        "- Stone pickaxe: (need wooden_pickaxe first) → mine cobblestone → cobblestone + sticks → stone_pickaxe",
        "- Iron pickaxe: (need stone_pickaxe first) → mine iron_ore → smelt in furnace → iron_ingot + sticks → iron_pickaxe",
        "- Furnace: (need wooden_pickaxe first) → mine 8 cobblestone → craft furnace",
        "- Torches: mine coal_ore (wooden_pickaxe) + craft sticks → torch",
        "",
        "### CRITICAL: Crafting table requirement",
        "- Most tools, weapons, and complex items REQUIRE a nearby crafting table.",
        "- Craft a crafting_table (4 planks) and place it BEFORE trying to craft tools.",
        "- If craft_items fails, you likely need to place a crafting table first.",
        "",
        "### Smelting requirements",
        "- Smelting requires: a placed furnace + fuel + the ore/item",
        "- Fuel priority: coal (best) > charcoal > logs/planks (worst)",
        "- Raw iron/gold/copper → ingots (must smelt, cannot use raw)",
        "- To get charcoal: smelt logs in furnace with another log as fuel",
        "",
        "### Survival reasoning checklist",
        "Before EVERY action, ask yourself:",
        "1. Do I have the required tool in my inventory? If not, what do I need to craft it?",
        "2. Do I have the materials to craft that tool? If not, what do I need to gather?",
        "3. Is there a crafting table placed nearby? If not, craft and place one.",
        "4. Am I at the right Y-level? (Diamonds: Y -59 to 16, Iron: Y -24 to 56)",
        "5. Do I have food? If health/food is low, eat first.",
        "",
        "### Progression order (never skip steps)",
        "Punch trees → craft wooden tools → mine stone → craft stone tools → "
        "mine coal + iron → build furnace → smelt iron → craft iron tools → mine diamonds",
    ]
    return "\n".join(lines)
