# Minecraft Dedalus MCP

LAN-oriented Minecraft MCP stack: Python MCP server + Node Mineflayer bridge. Control a bot via the Dedalus agent or in-game **chat as natural language commands**.

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
   Use your machine’s LAN IP for `--join-host` (or `127.0.0.1` if the world is on this machine). Use the port shown in-game for `--join-port`. Put `MINECRAFT_PORT` and `MINECRAFT_HOST` in `.env` to avoid passing `--join-*` each time.

4. **In Minecraft chat**, type natural language commands. Examples:
   - `mine 10 dirt`
   - `go to the tree`
   - `build a small pillar`
   - `attack the zombie`

The agent uses your local MCP server by default (`http://127.0.0.1:8000/mcp`). If you run in a setup where the agent cannot reach localhost (e.g. agent in the cloud), set `AGENT_MCP_URL` to a public URL (e.g. from `ngrok http 8000`).

---

## What this project is

- **Python MCP server** – Exposes Minecraft bot actions as MCP tools (move, mine, place, attack, craft, chat, etc.). Built on [dedalus_mcp](https://github.com/dedalus-labs/dedalus-mcp-python).
- **Node bridge** – Connects to a real Minecraft (Java) client via [Mineflayer](https://github.com/PrismarineJS/mineflayer). Handles pathfinding (including breaking/placing blocks in the way), digging, placing, combat, inventory.
- **Simulation mode** – Test the stack without a live game (simulated world and tools).

Result: point the Dedalus Python SDK (or any MCP client) at your local MCP server and control the bot; or use **in-game chat as commands** with the chat-driven agent.

---

## Requirements

- **Python 3.10+** (e.g. via `uv`)
- **Node 20+**, **npm 10+**
- **Minecraft Java Edition** for real LAN play (world opened to LAN, or a server)
- **Dedalus API key** for the agent (`DEDALUS_API_KEY` in `.env` or environment)
- **ngrok** (or similar) if you want the cloud agent to respond to in-game chat (so it can reach your MCP server)

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
| `MINECRAFT_PORT` | Minecraft server port (e.g. LAN port from “Open to LAN”) | `25565` → set to e.g. `61246` |
| `MINECRAFT_USERNAME` | Bot username in-game | `DedalusBot` |
| `AGENT_MCP_URL` | MCP URL the agent uses. Default is local (`http://127.0.0.1:8000/mcp`). Set to a public URL (e.g. ngrok + `/mcp`) only if the agent runs in the cloud and cannot reach localhost. | (optional; local URL by default) |
| `MCP_SERVER_URL` | Local MCP server URL for `run_tool.py`, `run_join_game.py`, etc. | `http://127.0.0.1:8000/mcp` |
| `DEDALUS_MODEL` | Model for the agent | `openai/gpt-5.2` |

Scripts that accept `--join-host` / `--join-port` use these as defaults when you don’t pass the flag. The MCP server’s `join_game` tool also uses `MINECRAFT_HOST` and `MINECRAFT_PORT` when the tool is called without host/port.

---

## Ways to run

### 1. One command: bridge + MCP + join + chat agent

Use this to get everything up and command the bot via chat:

```bash
export DEDALUS_API_KEY=your_key_here
uv run python run_live_chat.py --join-host YOUR_LAN_IP --join-port LAN_PORT --agent-mcp-url https://YOUR_NGROK_URL/mcp
```

- **Bridge** and **MCP server** start in the same process (logs prefixed with `[bridge]` / `[mcp]`).
- **Join game** is called automatically with `--join-host` and `--join-port`.
- **Chat agent** runs and polls in-game chat; each new player message is sent to the Dedalus agent as a goal.

Options:

- `--join-host` – Minecraft server host (default: `MINECRAFT_HOST` or `127.0.0.1`).
- `--join-port` – Minecraft server port (default: `MINECRAFT_PORT` or `25565`). For “Open to LAN”, use the in-game port.
- `--agent-mcp-url` – MCP URL the Dedalus agent uses (must be reachable from the internet for chat; e.g. ngrok URL + `/mcp`).
- `--username` – Bot username (default: `DedalusBot`).
- `--auth` – `microsoft` or `offline`.
- `--poll-interval` – Seconds between chat polls (default: 8).
- `--continue-after` – After this many agent runs, prompt “Continue? (y/n)” so you can stop before hitting rate limits (default: 100; use 0 to never prompt).
- `--rate-limit-wait` – When a rate-limit error is detected, wait this many seconds then offer to continue (default: 60).
- `--bridge-port`, `--server-port` – Ports for bridge (8787) and MCP server (8000).

If you don’t set `DEDALUS_API_KEY`, the launcher still starts the bridge and MCP server and tries to join; the chat agent won’t run. For local use, the default MCP URL is `http://127.0.0.1:8000/mcp`. Without chat, use `run_join_game.py` and `run_tool.py` from another terminal.

**Rate limits:** The chat agent counts how many times it has run the Dedalus agent. After `--continue-after` runs (default 100), it asks “Continue? (y/n)” so you can stop or keep going. If the API returns a rate-limit (or 429) error, it will prompt to wait (e.g. 60s) and try again. This lets the agent stay running while staying within reason.

---

### 2. Manual: bridge + MCP server in separate terminals

**Terminal 1 – Bridge**

```bash
npm --prefix bridge run start -- --listen-host 0.0.0.0 --listen-port 8787
```

**Terminal 2 – MCP server**

```bash
uv run python -m minecraft_dedalus_mcp.server --host 0.0.0.0 --port 8000 --bridge-url http://127.0.0.1:8787
```

**Terminal 3 – Join game** (world must be open to LAN)

```bash
uv run python run_join_game.py --host YOUR_LAN_IP --port LAN_PORT
```

**Terminal 4 (optional) – Chat-driven agent**

```bash
export DEDALUS_API_KEY=your_key_here
uv run python run_chat_agent.py --server-url https://YOUR_NGROK_URL/mcp
```

---

### 3. Simulation mode (no Minecraft)

Runs a simulated bridge + MCP server + one-off agent run (no real game):

```bash
export DEDALUS_API_KEY=your_key_here
uv run minecraft-dedalus-run-sim
```

Use `--skip-agent` to only start the stack and verify readiness.

---

## Commanding the bot

### From in-game chat (with chat agent running)

Type in Minecraft chat as a **different player** (not the bot). The bot will:

- **Acknowledge** in chat (e.g. `On it! [mine 10 dirt]`) when it picks up your message.
- **Log progress** in chat (e.g. `I'm doing this! [mining oak_log]`, `Moving to (10, 70, 0)`, `Done [mined 10 dirt]`) so you see what it’s doing.
- **Say when done** (e.g. `Done! [mine 10 dirt]`). If it hits a rate limit it may post `Pausing (rate limit), back in 60s...`.

Examples of commands to type:

- `mine 10 dirt`
- `go to 100 70 200`
- `build a 3x3 pillar`
- `attack the zombie`
- `craft oak_planks`

The agent maps these to MCP tools (e.g. `mine_resource`, `go_to_known_location`, `build_structure`, `attack_entity`, `craft_items`).

### From the CLI (`run_tool.py`)

With the bridge and MCP server (and bot) running:

```bash
uv run python run_tool.py get_bot_status
uv run python run_tool.py inspect_world '{"radius": 16}'
uv run python run_tool.py go_to_known_location '{"x": 0, "y": 70, "z": 0, "range": 2}'
uv run python run_tool.py mine_resource '{"name": "dirt", "count": 10}'
uv run python run_tool.py dig_block '{"x": 1, "y": 71, "z": 0}'
uv run python run_tool.py place_block '{"block": "cobblestone", "x": 2, "y": 72, "z": 0}'
uv run python run_tool.py attack_entity '{"name": "zombie", "count": 1}'
uv run python run_tool.py send_chat '{"message": "hello"}'
```

---

## MCP tools (reference)

Movement and world:

- **join_game** – Connect to a Minecraft server (host, port, username, auth).
- **leave_game** – Disconnect.
- **get_bot_status** – Position, health, food, inventory, nearby entities.
- **inspect_world** – Nearby blocks and entities (radius).
- **go_to_known_location** – Move to (x, y, z). Pathfinding can **break blocks and place scaffolding** (dirt/cobblestone) to reach the goal.

Blocks and items:

- **mine_resource** – Break and collect blocks by name (e.g. `oak_log`, `dirt`).
- **dig_block** – Break one block at (x, y, z).
- **place_block** – Place a block from inventory at (x, y, z).
- **get_block_at** – Block name at (x, y, z).
- **use_block** – Activate block at (x, y, z) (door, button, chest, etc.).
- **craft_items** – Craft item by name (e.g. `oak_planks`, `crafting_table`).

Inventory and player:

- **equip_item** – Equip item (hand, head, torso, legs, feet).
- **drop_item** – Drop item from inventory.
- **eat** – Consume food.

Movement and look:

- **look_at** – Look at (x, y, z).
- **jump** – Jump once.
- **set_sprint** / **set_sneak** – Sprint or sneak on/off.
- **stop_movement** – Stop pathfinding.

Entities:

- **attack_entity** – Attack by entity name (e.g. `zombie`, `player`).
- **mount_entity** / **dismount** – Mount/dismount entity (horse, boat, etc.).
- **interact_entity** – Interact (e.g. villager).

Other:

- **sleep** / **wake** – Sleep in bed at (x, y, z) / wake.
- **collect_items** – Pick up nearby dropped items.
- **fish** – Use fishing rod.
- **send_chat** / **read_chat** – Send or read in-game chat.
- **build_structure** – Build preset (pillar, wall, bridge, hut) with material at origin.
- **recommend_next_goal** – Get a suggested next survival/building goal.

---

## Scripts in this repo

| Script | Purpose |
|--------|---------|
| **run_live_chat.py** | One command: start bridge, MCP, join game, run chat agent. Command the bot via in-game chat. |
| **run_chat_agent.py** | Poll chat and run the Dedalus agent on each new player message (requires bridge + MCP + bot in game). |
| **run_join_game.py** | Call `join_game` once (host/port via args or `MINECRAFT_HOST`, `MINECRAFT_PORT`). |
| **run_tool.py** | Call any MCP tool from the CLI (e.g. `run_tool.py mine_resource '{"name": "dirt", "count": 5}'`). |
| **run_agent_live.py** | Run the Dedalus agent once with a goal (no chat polling). |
| **run_demo_move.py** | Demo: move the bot 5 blocks east. |
| **run_demo_break.py** | Demo: break one nearby block. |
| **run_demo_attack_player.py** | Demo: attack another player until they’re gone. |

---

## Troubleshooting

- **Agent says “MCP server unavailable”**  
  The Dedalus agent runs in the cloud and must reach your MCP server. Use a public URL (e.g. **ngrok**: `ngrok http 8000`) and pass `--agent-mcp-url https://YOUR_NGROK_URL/mcp` to `run_live_chat.py` or `run_chat_agent.py`.

- **ENETUNREACH or ECONNREFUSED when joining**  
  Wrong host/port or the game isn’t open to LAN. Use your machine’s LAN IP and the port shown in-game. For “Open to LAN” on the same machine, try `--join-host 192.168.x.x` (your LAN IP) and the in-game port.

- **go_to_known_location: “Cannot read properties of undefined (reading 'GoalNear')”**  
  Fixed in the bridge (pathfinder ESM default export). Ensure you have the latest bridge code.

- **mine_resource returns mined: 0**  
  No matching block in range, or block name doesn’t match your version. Use `inspect_world` to see block names; for 1.20+ use e.g. `oak_log`, `dirt`.

- **Chat commands don’t do anything**  
  Ensure the chat agent is running with a **public** MCP URL (`--agent-mcp-url` with ngrok). Set `DEDALUS_API_KEY`. Messages must be from another player (not the bot).

---

## Project layout

```
bridge/                 Node Mineflayer bridge (real + simulate)
src/minecraft_dedalus_mcp/   MCP server, bridge client, playbook, agent_demo
run_live_chat.py         One-command launcher (bridge + MCP + join + chat agent)
run_chat_agent.py        Chat polling + Dedalus agent
run_join_game.py         Join game once
run_tool.py              Call any MCP tool from CLI
docs/research.md         Research notes
tests/                   Pytest (e2e with sim bridge)
```

---

## Limitations

- Simulation mode tests tool flow, not real Mineflayer physics.
- Real bridge supports core survival actions but is not a full “Voyager-style” stack.
- Beating the game is expressed as a playbook and agent workflow, not a single guaranteed run.
