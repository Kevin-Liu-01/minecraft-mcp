# Minecraft Dedalus MCP

LAN-oriented Minecraft MCP stack: Python MCP server + Node Mineflayer bridge. Control a bot via the Dedalus agent or in-game **chat as natural language commands**.

**New in v2:** Skill library, multi-step planning, persistent world memory, freeform building from natural language, smelting/furnace automation, error recovery with retry, and a creative/survival mode toggle.

---

## Quick start (one command)

Get everything running and command the bot from **in-game chat**:

1. **Open Minecraft Java Edition**, start a world, and click **Open to LAN**. Note the port (e.g. `61246`).

2. **Expose your MCP server** so the cloud agent can reach it (required for chat commands):
   ```bash
   ngrok http 8000
   ```
   Copy the `https://...` URL (e.g. `https://abc123.ngrok.io`).

3. **Run the one-command launcher** (bridge + MCP server + join game + chat agent):
   ```bash
   export DEDALUS_API_KEY=your_key_here
   uv run python run_live_chat.py --join-host 192.168.68.70 --join-port 61246
   ```
   Use your machine's LAN IP for `--join-host` (or `127.0.0.1` if the world is on this machine). Use the port shown in-game for `--join-port`. Put `MINECRAFT_PORT` and `MINECRAFT_HOST` in `.env` to avoid passing `--join-*` each time.

4. **In Minecraft chat**, type natural language commands. Examples:
   - `mine 10 dirt`
   - `go to the tree`
   - `build a 5x5 house with oak planks`
   - `attack the zombie`
   - `switch to creative mode and give me 64 diamonds`
   - `create a plan to get iron tools`

---

## What this project is

- **Python MCP server** – Exposes 60+ Minecraft bot actions as MCP tools (move, mine, place, attack, craft, chat, plan, remember, build, smelt, and more). Built on [dedalus_mcp](https://github.com/dedalus-labs/dedalus-mcp-python).
- **Node bridge** – Connects to a real Minecraft (Java) client via [Mineflayer](https://github.com/PrismarineJS/mineflayer). Handles pathfinding (including breaking/placing blocks in the way), digging, placing, combat, inventory, smelting, and slash commands.
- **Simulation mode** – Test the stack without a live game (simulated world and tools).
- **Skill library** – Save and reuse multi-step tool sequences (Voyager-inspired).
- **Multi-step planner** – Decompose goals into checkpointed execution plans.
- **World memory** – Persistent storage of locations, resources, and structures across sessions.
- **Creative/Survival modes** – Creative mode unlocks teleport, give, fill, summon, time, weather. Survival mode keeps legit pathfinding and resource gathering.
- **Freeform building** – Describe structures in natural language (house, tower, bridge, farm, stairs, fence, pool, platform, pillar).
- **Error recovery** – Automatic retries with alternative positions and resources when tools fail.
- **Autonomous survival mode** – Say "start autonomous" in chat and the bot plays the game on its own (inspect → plan → execute → learn). Say "stop" to return to command mode.

---

## Requirements

- **Python 3.10+** (e.g. via `uv`)
- **Node 20+**, **npm 10+**
- **Minecraft Java Edition** for real LAN play (world opened to LAN, or a server)
- **Dedalus API key** for the agent (`DEDALUS_API_KEY` in `.env` or environment)
- **ngrok** (or similar) if you want the cloud agent to respond to in-game chat

---

## Setup

```bash
uv sync --extra dev
npm --prefix bridge install
```

Copy the example env file and fill in your values:

```bash
cp .env.example .env
# Edit .env: set DEDALUS_API_KEY, MINECRAFT_PORT (e.g. your LAN port), etc.
```

### Environment variables (`.env` format)

| Variable | Purpose | Default / example |
|----------|---------|-------------------|
| `DEDALUS_API_KEY` | Dedalus API key (required for chat agent) | (required) |
| `MINECRAFT_HOST` | Minecraft server host for `join_game` | `127.0.0.1` |
| `MINECRAFT_PORT` | Minecraft server port (e.g. LAN port from "Open to LAN") | `25565` → set to e.g. `61246` |
| `MINECRAFT_USERNAME` | Bot username in-game | `DedalusBot` |
| `AGENT_MCP_URL` | MCP URL the agent uses. Default is local. Set to public URL for cloud agent. | (optional) |
| `MCP_SERVER_URL` | Local MCP server URL for scripts | `http://127.0.0.1:8000/mcp` |
| `DEDALUS_MODEL` | Model for the agent | `openai/gpt-5.2` |
| `MINECRAFT_MCP_DATA_DIR` | Directory for persistent data (skills, memory, plans, session) | `.minecraft_mcp_data` |

---

## Ways to run

### 1. One command: bridge + MCP + join + chat agent

```bash
export DEDALUS_API_KEY=your_key_here
uv run python run_live_chat.py --join-host YOUR_LAN_IP --join-port LAN_PORT --agent-mcp-url https://YOUR_NGROK_URL/mcp
```

### 2. Manual: bridge + MCP server in separate terminals

**Terminal 1 – Bridge**

```bash
npm --prefix bridge run start -- --listen-host 0.0.0.0 --listen-port 8787
```

**Terminal 2 – MCP server**

```bash
uv run python -m minecraft_dedalus_mcp.server --host 0.0.0.0 --port 8000 --bridge-url http://127.0.0.1:8787
```

**Terminal 3 – Join game**

```bash
uv run python run_join_game.py --host YOUR_LAN_IP --port LAN_PORT
```

### 3. Simulation mode (no Minecraft)

```bash
export DEDALUS_API_KEY=your_key_here
uv run minecraft-dedalus-run-sim
```

---

## MCP Tools (60+)

### Core Actions

| Category | Tools |
|----------|-------|
| **Connection** | `join_game`, `leave_game` |
| **Status** | `get_bot_status`, `inspect_world`, `get_block_at` |
| **Movement** | `go_to_known_location`, `look_at`, `jump`, `set_sprint`, `set_sneak`, `stop_movement`, `safe_move_to` |
| **Mining** | `mine_resource`, `dig_block` |
| **Building** | `place_block`, `use_block`, `build_structure`, `build_from_description` |
| **Crafting** | `craft_items`, `smelt_item` |
| **Inventory** | `equip_item`, `drop_item`, `eat`, `auto_eat`, `ensure_has_item` |
| **Entities** | `attack_entity`, `mount_entity`, `dismount`, `interact_entity` |
| **Other** | `sleep`, `wake`, `collect_items`, `fish`, `send_chat`, `read_chat` |

### Planning & Intelligence

| Category | Tools |
|----------|-------|
| **Planning** | `create_plan`, `get_plan_status`, `get_next_plan_step`, `complete_plan_step`, `fail_plan_step`, `list_plans` |
| **Skills** | `save_skill`, `find_skills`, `get_skill`, `list_skills`, `record_skill_success`, `remove_skill` |
| **Memory** | `remember_location`, `recall_locations`, `find_nearest_location`, `remember_resource`, `find_resource`, `get_memory_summary` |
| **Session** | `get_session_summary`, `get_recent_actions`, `get_recent_failures` |
| **Recovery** | `execute_with_recovery` |
| **Playbook** | `recommend_next_goal` |

### Creative Mode (requires `set_mode('creative')`)

| Tool | Description |
|------|-------------|
| `set_mode` | Switch between `creative` and `survival` |
| `get_mode` | Check current mode |
| `run_command` | Execute any slash command |
| `teleport` | Instant teleport to (x, y, z) |
| `give_item` | Give items to bot |
| `fill_blocks` | Fill a volume with blocks |
| `set_time` | Set time of day |
| `set_weather` | Set weather |
| `summon_entity` | Spawn entities |
| `kill_entities` | Kill entities by selector |

---

## Freeform Building

Describe a structure in natural language with `build_from_description`:

```bash
uv run python run_tool.py build_from_description '{"description": "a 7x7x5 house with a door", "origin_x": 10, "origin_y": 64, "origin_z": 10, "material": "oak_planks"}'
```

**Supported structure types:** house, cottage, cabin, tower, turret, wall, bridge, platform, floor, stairs, steps, fence, enclosure, pool, farm, pillar.

**Dimensions:** Include `WxLxH` (e.g. `5x5x4`) in the description for custom sizes. Defaults to 5x5x4.

---

## Multi-Step Planning

Create plans that decompose goals into tool-call steps:

```bash
# Create a plan
uv run python run_tool.py create_plan '{"goal": "get stone tools"}'

# Check status
uv run python run_tool.py get_plan_status '{"plan_id": "abc123"}'

# Get next step to execute
uv run python run_tool.py get_next_plan_step '{"plan_id": "abc123"}'
```

**Built-in plan templates:** `gather_wood`, `get_stone_tools`, `get_iron_tools`, `build_shelter`, `hunt_food`, `explore_area`, `prepare_nether`.

---

## Skill Library

Save reusable tool sequences and retrieve them by keyword:

```bash
# Save a skill
uv run python run_tool.py save_skill '{"name": "early_game", "description": "Get wood, craft tools", "tool_sequence": "[{\"tool\": \"mine_resource\", \"args\": {\"name\": \"oak_log\", \"count\": 4}}]", "tags": "early,tools"}'

# Find skills
uv run python run_tool.py find_skills '{"query": "wood crafting"}'
```

---

## Creative Mode

Switch to creative mode to use god-mode commands:

```bash
# Switch to creative
uv run python run_tool.py set_mode '{"mode": "creative"}'

# Teleport instantly
uv run python run_tool.py teleport '{"x": 100, "y": 80, "z": 100}'

# Give items
uv run python run_tool.py give_item '{"item": "diamond_block", "count": 64}'

# Fill a volume
uv run python run_tool.py fill_blocks '{"x1": 0, "y1": 64, "z1": 0, "x2": 10, "y2": 64, "z2": 10, "block": "gold_block"}'

# Switch back to survival
uv run python run_tool.py set_mode '{"mode": "survival"}'
```

Creative tools return errors if called while in survival mode. The bot retains its pathfinding, planning, memory, and skill capabilities in both modes.

---

## Autonomous Survival Mode

The bot can play the game on its own — proactively inspecting the world, setting goals, planning, executing, and learning. It only activates when you tell it to, and stops on command.

### From in-game chat

```
start autonomous     → bot starts playing on its own
stop                 → bot stops and waits for commands
mine 10 dirt         → any direct command also stops autonomous mode
start autonomous     → resume autonomous play
```

Trigger phrases: `start autonomous`, `play on your own`, `survive`, `do your thing`, `autoplay`.
Stop phrases: `stop`, `pause`, `halt`, `wait`, `come here`.

### How it works

Each autonomous cycle:
1. **Inspect** — calls `recommend_next_goal` to decide what to do
2. **Plan** — the LLM agent sees the goal + all 60+ tools and decides its approach
3. **Execute** — runs up to 25 tool calls per cycle (mine, craft, build, fight, smelt, etc.)
4. **Learn** — saves locations, resources, skills from successful sequences
5. **Repeat** — waits 5 seconds, then starts the next cycle

The bot announces what it's doing in chat so you can watch. Rate limits are handled automatically (pauses and retries).

### Standalone demo (no chat polling)

```bash
uv run python run_demo_autonomous.py
```

Press Ctrl+C to stop.

---

## Demo Scripts

| Script | What it demos |
|--------|---------------|
| **run_demo_autonomous.py** | Autonomous survival: bot plays on its own until stopped |
| **run_demo_skill_library.py** | Save, search, and retrieve reusable skills |
| **run_demo_planning.py** | Create plans, execute steps, track progress |
| **run_demo_memory.py** | Remember locations, resources; recall across sessions |
| **run_demo_freeform_build.py** | Build houses, towers, bridges, farms from descriptions |
| **run_demo_smelt.py** | Furnace smelting (raw iron → iron ingot) |
| **run_demo_error_recovery.py** | Auto-retry with alternative positions/resources |
| **run_demo_creative.py** | Creative mode commands: teleport, give, fill, summon |
| **run_demo_full_agent.py** | Full workflow: plan → execute → remember → save skill → build |
| **run_demo_move.py** | Move the bot 5 blocks east |
| **run_demo_break.py** | Break one nearby block |
| **run_demo_attack_player.py** | Attack another player until they're gone |

Run any demo (with bridge + MCP server running):

```bash
uv run python run_demo_skill_library.py
uv run python run_demo_creative.py
uv run python run_demo_full_agent.py
```

---

## Persistent Data

The MCP server stores data in `MINECRAFT_MCP_DATA_DIR` (default `.minecraft_mcp_data/`):

| File | Contents |
|------|----------|
| `skills.json` | Saved skill library |
| `world_memory.json` | Locations, resources, structures |
| `session_history.json` | Action log (last 500 actions) |
| `plans.json` | Task plans with step status |

Data persists across server restarts. Delete the directory to start fresh.

---

## Project layout

```
bridge/                         Node Mineflayer bridge (real + simulate)
src/minecraft_dedalus_mcp/
  ├── server.py                 MCP server + 60+ tool definitions
  ├── bridge_client.py          HTTP client to bridge
  ├── models.py                 Pydantic models
  ├── constants.py              Domain constants
  ├── playbook.py               Survival goal recommendations
  ├── skills/
  │   └── store.py              Skill library (save, find, replay)
  ├── planning/
  │   ├── planner.py            Multi-step task planner with checkpoints
  │   └── blueprints.py         Freeform building (NL → block plans)
  ├── memory/
  │   ├── world_memory.py       Persistent world knowledge
  │   └── session.py            Session action history
  ├── modes/
  │   ├── base.py               Game mode manager
  │   ├── creative.py           Creative mode actions
  │   └── survival.py           Survival mode helpers
  └── recovery/
      └── retry.py              Error recovery with retry strategies
run_live_chat.py                One-command launcher
run_chat_agent.py               Chat polling + agent
run_demo_*.py                   Demo scripts for each capability
tests/                          Pytest (e2e with sim bridge)
docs/research.md                Research notes
```

---

## Troubleshooting

- **Agent says "MCP server unavailable"** — Use ngrok and pass `--agent-mcp-url`.
- **ENETUNREACH or ECONNREFUSED** — Wrong host/port or game isn't open to LAN.
- **mine_resource returns mined: 0** — Block name mismatch. Use `inspect_world` to check names.
- **Creative tools return "requires creative mode"** — Call `set_mode('creative')` first.
- **Smelting fails** — Ensure a furnace is placed nearby and fuel + items are in inventory.

---

## Limitations

- Simulation mode tests tool flow, not real Mineflayer physics.
- Freeform building generates deterministic blueprints from keywords; truly novel shapes require extending `blueprints.py`.
- Creative mode requires the bot to have operator permissions on the server for slash commands.
- Smelting waits a fixed time for output; very large batches may time out.
- Skill library uses keyword search, not embeddings (simple and fast, but less semantic).
