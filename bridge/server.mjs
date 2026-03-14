import http from "node:http";
import { once } from "node:events";
import { URL } from "node:url";

import { Vec3 } from "vec3";
import { getPreset, listPresets } from "./presets.mjs";


const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8787;


function parseArgs(argv) {
  const args = {
    host: DEFAULT_HOST,
    port: DEFAULT_PORT,
    simulate: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--listen-host" && argv[i + 1]) {
      args.host = argv[i + 1];
      i += 1;
    } else if (token === "--listen-port" && argv[i + 1]) {
      args.port = Number(argv[i + 1]);
      i += 1;
    } else if (token === "--simulate") {
      args.simulate = true;
    }
  }

  return args;
}


function jsonResponse(res, statusCode, payload) {
  res.writeHead(statusCode, { "content-type": "application/json" });
  res.end(JSON.stringify(payload));
}


function parseBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk.toString("utf8");
    });
    req.on("end", () => {
      if (!raw) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(new Error(`Invalid JSON body: ${error.message}`));
      }
    });
    req.on("error", reject);
  });
}


function nowIso() {
  return new Date().toISOString();
}


function clampPositiveInt(value, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.floor(parsed);
}


function inventoryToList(inventoryMap) {
  return Object.entries(inventoryMap)
    .filter(([, count]) => count > 0)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([item, count]) => ({ item, count }));
}


function buildPlanFromPreset({
  preset,
  material,
  originX,
  originY,
  originZ,
  width,
  length,
  height,
}) {
  const gen = getPreset(preset);
  if (!gen) throw new Error(`Unknown preset: ${preset}. Available: ${listPresets().join(", ")}`);
  return gen(originX, originY, originZ, { width, length, height, material });
}


// Chat message types:
//   "player"  – message from another player in the game
//   "system"  – server/game notification (death, achievement, join/leave, etc.)
//   "self"    – message sent by this bot
const CHAT_TYPE_PLAYER = "player";
const CHAT_TYPE_SYSTEM = "system";
const CHAT_TYPE_SELF = "self";


class SimulationSession {
  constructor() {
    this.connected = false;
    this.config = null;
    this.position = { x: 0, y: 64, z: 0 };
    this.health = 20;
    this.food = 20;
    this.inventory = {};
    this.chatLog = [];
    this.world = new Map();
    this.entities = [
      { name: "cow", kind: "passive", x: 6, y: 64, z: 4 },
      { name: "enderman", kind: "neutral", x: 12, y: 64, z: -8 },
      { name: "blaze", kind: "hostile", x: 24, y: 70, z: 24 },
    ];
    this.availableResources = {
      oak_log: 64,
      cobblestone: 128,
      coal: 32,
      iron_ore: 48,
      blaze_rod: 6,
      ender_pearl: 8,
    };
  }

  _setWorldBlock(x, y, z, block) {
    this.world.set(`${x},${y},${z}`, block);
  }

  _getWorldBlocks(limit = 32) {
    return Array.from(this.world.entries())
      .slice(0, limit)
      .map(([key, block]) => {
        const [x, y, z] = key.split(",").map(Number);
        return { name: block, x, y, z };
      });
  }

  _count(item) {
    return this.inventory[item] || 0;
  }

  _add(item, count) {
    this.inventory[item] = this._count(item) + count;
  }

  _consume(item, count) {
    const current = this._count(item);
    if (current < count) {
      throw new Error(`Not enough ${item}. Need ${count}, have ${current}.`);
    }
    this.inventory[item] = current - count;
    if (this.inventory[item] <= 0) {
      delete this.inventory[item];
    }
  }

  _pushChat(sender, message, type = CHAT_TYPE_SYSTEM) {
    this.chatLog.push({ sender, message, type, timestamp: nowIso() });
    this.chatLog = this.chatLog.slice(-100);
  }

  async connect(config) {
    this.connected = true;
    this.config = {
      host: config.host || "127.0.0.1",
      port: clampPositiveInt(config.port, 25565),
      username: config.username || "DedalusBot",
      auth: config.auth || "offline",
      version: config.version || null,
    };
    this.position = { x: 0, y: 64, z: 0 };
    this.health = 20;
    this.food = 20;
    this.inventory = {
      dirt: 32,
      cobblestone: 16,
    };
    this.chatLog = [];
    this.world = new Map();
    this._pushChat("server", `${this.config.username} joined the simulated world`);
    return this.status();
  }

  async disconnect() {
    if (this.connected) {
      this._pushChat("server", `${this.config.username} left the simulated world`);
    }
    this.connected = false;
    this.config = null;
    return { connected: false };
  }

  async status() {
    return {
      connected: this.connected,
      mode: "simulate",
      username: this.config?.username || null,
      host: this.config?.host || null,
      port: this.config?.port || null,
      position: this.position,
      health: this.health,
      food: this.food,
      inventory: inventoryToList(this.inventory),
      entities: this.entities.slice(0, 8).map((entity) => ({
        name: entity.name,
        kind: entity.kind,
        x: entity.x,
        y: entity.y,
        z: entity.z,
      })),
      chat_backlog: this.chatLog.length,
    };
  }

  async inspectWorld({ radius = 16 } = {}) {
    return {
      radius,
      position: this.position,
      visible_blocks: [
        ...Object.entries(this.availableResources)
          .filter(([, count]) => count > 0)
          .map(([name, count]) => ({ name, count })),
        ...this._getWorldBlocks(24),
      ].slice(0, 24),
      nearby_entities: this.entities.slice(0, 8),
      objectives: [
        "Gather wood for early crafting",
        "Upgrade to stone then iron tools",
        "Prepare nether travel and blaze rods",
      ],
    };
  }

  async moveTo({ x, y, z, range = 1 }) {
    this.position = { x, y, z };
    return {
      reached: true,
      range,
      position: this.position,
    };
  }

  async mineResource({ name, count = 1 }) {
    const available = this.availableResources[name] || 0;
    if (available <= 0) {
      throw new Error(`No ${name} remaining in the simulated world.`);
    }
    const mined = Math.min(count, available);
    this.availableResources[name] = available - mined;
    const inventoryItem = name === "iron_ore" ? "raw_iron" : name;
    this._add(inventoryItem, mined);
    return {
      action: "mine_resource",
      resource: name,
      mined,
      inventory: inventoryToList(this.inventory),
    };
  }

  async craftItems({ item, count = 1 }) {
    const recipes = {
      oak_planks: { oak_log: 1, output: 4 },
      stick: { oak_planks: 2, output: 4 },
      crafting_table: { oak_planks: 4, output: 1 },
      wooden_pickaxe: { oak_planks: 3, stick: 2, output: 1 },
      stone_pickaxe: { cobblestone: 3, stick: 2, output: 1 },
      furnace: { cobblestone: 8, output: 1 },
      iron_pickaxe: { iron_ingot: 3, stick: 2, output: 1 },
      shield: { iron_ingot: 1, oak_planks: 6, output: 1 },
      eye_of_ender: { blaze_powder: 1, ender_pearl: 1, output: 1 },
      blaze_powder: { blaze_rod: 1, output: 2 },
    };

    const recipe = recipes[item];
    if (!recipe) {
      throw new Error(`No simulated recipe for ${item}.`);
    }

    const output = recipe.output;
    const batches = Math.ceil(count / output);
    for (const [ingredient, amount] of Object.entries(recipe)) {
      if (ingredient === "output") {
        continue;
      }
      this._consume(ingredient, amount * batches);
    }
    this._add(item, output * batches);

    return {
      action: "craft_items",
      item,
      crafted: output * batches,
      requested: count,
      inventory: inventoryToList(this.inventory),
    };
  }

  async placeBlock({ block, x, y, z }) {
    this._consume(block, 1);
    this._setWorldBlock(x, y, z, block);
    return {
      action: "place_block",
      block,
      position: { x, y, z },
      inventory: inventoryToList(this.inventory),
    };
  }

  async digBlock({ x, y, z }) {
    const key = `${x},${y},${z}`;
    const block = this.world.get(key);
    if (!block) {
      throw new Error(`No placed block at ${key}.`);
    }
    this.world.delete(key);
    this._add(block, 1);
    return {
      action: "dig_block",
      block,
      position: { x, y, z },
      inventory: inventoryToList(this.inventory),
    };
  }

  async attackEntity({ name, count = 1 }) {
    const defeated = [];
    for (let index = this.entities.length - 1; index >= 0 && defeated.length < count; index -= 1) {
      if (this.entities[index].name === name) {
        defeated.push(this.entities[index]);
        this.entities.splice(index, 1);
      }
    }

    if (defeated.length === 0) {
      throw new Error(`No entity named ${name} found.`);
    }

    if (name === "enderman") {
      this._add("ender_pearl", defeated.length);
    } else if (name === "blaze") {
      this._add("blaze_rod", defeated.length);
    }

    return {
      action: "attack_entity",
      target: name,
      defeated: defeated.length,
      inventory: inventoryToList(this.inventory),
    };
  }

  async sendChat({ message }) {
    this._pushChat(this.config?.username || "DedalusBot", message, CHAT_TYPE_SELF);
    return {
      action: "send_chat",
      message,
      chat_messages: this.chatLog.slice(-10),
    };
  }

  async readChat({ limit = 20 }) {
    return {
      messages: this.chatLog.slice(-limit),
    };
  }

  async buildStructure(request) {
    const width = clampPositiveInt(request.width, 5);
    const length = clampPositiveInt(request.length, 5);
    const height = clampPositiveInt(request.height, 4);
    const steps = buildPlanFromPreset({
      preset: request.preset,
      material: request.material,
      originX: request.origin_x,
      originY: request.origin_y,
      originZ: request.origin_z,
      width,
      length,
      height,
    });
    this._consume(request.material, steps.length);
    for (const step of steps) {
      this._setWorldBlock(step.x, step.y, step.z, step.block);
    }
    return {
      action: "build_structure",
      preset: request.preset,
      material: request.material,
      blocks_placed: steps.length,
      inventory: inventoryToList(this.inventory),
      preview: this._getWorldBlocks(24),
    };
  }

  async getBlockAt({ x, y, z }) {
    const key = `${x},${y},${z}`;
    const block = this.world.get(key);
    return { action: "get_block_at", position: { x, y, z }, name: block ?? "air", simulated: true };
  }

  async useBlock({ x, y, z }) {
    return { action: "use_block", position: { x, y, z }, simulated: true };
  }

  async equipItem({ item, destination = "hand" }) {
    return { action: "equip_item", item, destination, inventory: inventoryToList(this.inventory), simulated: true };
  }

  async dropItem({ item, count = 1 }) {
    return { action: "drop_item", item, count, inventory: inventoryToList(this.inventory), simulated: true };
  }

  async eat({ item }) {
    return { action: "eat", item, inventory: inventoryToList(this.inventory), simulated: true };
  }

  async lookAt({ x, y, z }) {
    return { action: "look_at", position: { x, y, z }, simulated: true };
  }

  async jump() {
    return { action: "jump", simulated: true };
  }

  async setSprint({ sprint = true }) {
    return { action: "set_sprint", sprint, simulated: true };
  }

  async setSneak({ sneak = true }) {
    return { action: "set_sneak", sneak, simulated: true };
  }

  async sleep({ x, y, z }) {
    return { action: "sleep", position: { x, y, z }, simulated: true };
  }

  async wake() {
    return { action: "wake", simulated: true };
  }

  async collectItems({ radius = 8 }) {
    return { action: "collect_items", collected: 0, radius, inventory: inventoryToList(this.inventory), simulated: true };
  }

  async fish() {
    return { action: "fish", inventory: inventoryToList(this.inventory), simulated: true };
  }

  async mountEntity({ name }) {
    return { action: "mount_entity", target: name, simulated: true };
  }

  async dismount() {
    return { action: "dismount", simulated: true };
  }

  async interactEntity({ name }) {
    return { action: "interact_entity", target: name, simulated: true };
  }

  async stopMovement() {
    return { action: "stop_movement", simulated: true };
  }

  async findPlayers() {
    const players = this.entities.filter((e) => e.kind === "player");
    return { players };
  }

  async smeltItem({ item, count = 1, fuel = "coal" }) {
    const smeltMap = {
      raw_iron: "iron_ingot",
      raw_gold: "gold_ingot",
      raw_copper: "copper_ingot",
      iron_ore: "iron_ingot",
      sand: "glass",
      cobblestone: "stone",
      beef: "cooked_beef",
      porkchop: "cooked_porkchop",
      chicken: "cooked_chicken",
    };
    const output = smeltMap[item];
    if (!output) {
      throw new Error(`No smelting recipe for ${item}.`);
    }
    this._consume(item, count);
    this._consume(fuel, Math.ceil(count / 8));
    this._add(output, count);
    return {
      action: "smelt_item",
      input: item,
      output,
      count,
      fuel,
      inventory: inventoryToList(this.inventory),
    };
  }

  async runCommand({ command }) {
    this._pushChat("server", `Executed: ${command}`);
    return { action: "run_command", command, simulated: true };
  }

  async buildBlueprint({ blocks }) {
    let placed = 0;
    for (const entry of blocks) {
      if (this._count(entry.block) > 0) {
        this._consume(entry.block, 1);
      }
      this._setWorldBlock(entry.x, entry.y, entry.z, entry.block);
      placed += 1;
    }
    return {
      action: "build_blueprint",
      blocks_placed: placed,
      inventory: inventoryToList(this.inventory),
    };
  }
}


class MineflayerSession {
  constructor() {
    this.bot = null;
    this.registry = null;
    this.pathfinder = null;
    this.chatLog = [];
    this.config = null;
    this._pathLock = Promise.resolve();
    this._stopped = false;
  }

  _checkStopped() {
    if (this._stopped) {
      this._stopped = false;
      throw new Error("Action stopped by user.");
    }
  }

  _withPathLock(fn) {
    const next = this._pathLock.then(fn, fn);
    this._pathLock = next.catch(() => {});
    return next;
  }

  _requireBot() {
    if (!this.bot) {
      throw new Error("Bot is not connected. Call /session/connect first.");
    }
    return this.bot;
  }

  _inventory() {
    const bot = this._requireBot();
    return bot.inventory
      .items()
      .map((item) => ({ item: item.name, count: item.count }))
      .sort((a, b) => a.item.localeCompare(b.item));
  }

  _pushChat(sender, message, type = CHAT_TYPE_SYSTEM) {
    this.chatLog.push({ sender, message, type, timestamp: nowIso() });
    this.chatLog = this.chatLog.slice(-100);
  }

  async connect(config) {
    if (this.bot) {
      await this.disconnect();
    }

    const mineflayer = await import("mineflayer");
    const pathfinderPkg = await import("mineflayer-pathfinder");
    const minecraftDataModule = await import("minecraft-data");
    const pathfinderApi = pathfinderPkg.default ?? pathfinderPkg;

    const bot = mineflayer.createBot({
      host: config.host || "127.0.0.1",
      port: clampPositiveInt(config.port, 25565),
      username: config.username || "DedalusBot",
      auth: config.auth || "offline",
      version: config.version || false,
      checkTimeoutInterval: 300000,
    });

    bot.loadPlugin(pathfinderApi.pathfinder);

    bot.on("chat", (username, message) => {
      if (username !== bot.username) {
        this._pushChat(username, message, CHAT_TYPE_PLAYER);
      }
    });

    bot.on("messagestr", (message, messagePosition) => {
      if (messagePosition === "chat") return;
      this._pushChat("server", message, CHAT_TYPE_SYSTEM);
    });

    bot.once("error", (error) => {
      this._pushChat("error", error.message, CHAT_TYPE_SYSTEM);
    });

    await once(bot, "spawn");

    this.bot = bot;
    this.pathfinder = pathfinderApi;
    this.registry = minecraftDataModule.default(bot.version);
    this.config = {
      host: config.host || "127.0.0.1",
      port: clampPositiveInt(config.port, 25565),
      username: config.username || "DedalusBot",
      auth: config.auth || "offline",
      version: config.version || bot.version,
    };

    return this.status();
  }

  async disconnect() {
    if (this.bot) {
      try {
        this.bot.quit();
      } catch (error) {
        this._pushChat("error", error.message, CHAT_TYPE_SYSTEM);
      }
    }
    this.bot = null;
    this.registry = null;
    this.pathfinder = null;
    this.config = null;
    return { connected: false };
  }

  async status() {
    if (!this.bot) {
      return {
        connected: false,
        mode: "real",
      };
    }

    const bot = this._requireBot();
    return {
      connected: true,
      mode: "real",
      username: bot.username,
      host: this.config?.host || null,
      port: this.config?.port || null,
      position: {
        x: Math.floor(bot.entity.position.x),
        y: Math.floor(bot.entity.position.y),
        z: Math.floor(bot.entity.position.z),
      },
      health: bot.health,
      food: bot.food,
      inventory: this._inventory(),
      entities: this._nearbyEntities(),
      chat_backlog: this.chatLog.length,
    };
  }

  _nearbyEntities(limit = 8) {
    const bot = this._requireBot();
    const seen = new Set();
    const result = [];

    for (const entity of Object.values(bot.entities)) {
      if (entity === bot.entity) continue;
      const name = entity.name || entity.username || entity.type;
      seen.add(entity.username || name);
      result.push({
        name,
        kind: entity.type,
        x: Math.floor(entity.position.x),
        y: Math.floor(entity.position.y),
        z: Math.floor(entity.position.z),
      });
    }

    for (const [username, playerData] of Object.entries(bot.players)) {
      if (username === bot.username || seen.has(username)) continue;
      const entry = { name: username, kind: "player", x: null, y: null, z: null };
      if (playerData.entity && playerData.entity.position) {
        entry.x = Math.floor(playerData.entity.position.x);
        entry.y = Math.floor(playerData.entity.position.y);
        entry.z = Math.floor(playerData.entity.position.z);
      }
      result.push(entry);
    }

    return result.slice(0, limit);
  }

  _context() {
    const bot = this._requireBot();
    return {
      position: {
        x: Math.floor(bot.entity.position.x),
        y: Math.floor(bot.entity.position.y),
        z: Math.floor(bot.entity.position.z),
      },
      health: bot.health,
      food: bot.food,
      inventory: this._inventory(),
    };
  }

  async _autoEat() {
    const bot = this._requireBot();
    if (bot.food > 6) return;
    const foods = bot.inventory.items().filter((i) =>
      ["cooked_beef", "cooked_porkchop", "cooked_chicken", "cooked_mutton",
       "cooked_salmon", "cooked_cod", "bread", "golden_carrot", "golden_apple",
       "apple", "melon_slice", "baked_potato", "cooked_rabbit", "sweet_berries",
       "cookie", "pumpkin_pie", "beetroot_soup", "mushroom_stew", "rabbit_stew",
       "carrot", "potato", "beetroot", "dried_kelp", "raw_beef", "raw_porkchop",
       "raw_chicken", "raw_mutton", "raw_cod", "raw_salmon", "raw_rabbit",
       "rotten_flesh", "spider_eye"].includes(i.name)
    );
    if (foods.length === 0) return;
    const best = foods.sort((a, b) => b.foodPoints - a.foodPoints)[0] || foods[0];
    try {
      await bot.equip(best, "hand");
      await bot.consume();
    } catch (_) { /* ignore eat failures */ }
  }

  _bestToolFor(blockName) {
    const bot = this._requireBot();
    const pickaxeBlocks = new Set([
      "stone", "cobblestone", "sandstone", "coal_ore", "copper_ore", "iron_ore",
      "gold_ore", "diamond_ore", "redstone_ore", "emerald_ore", "lapis_ore",
      "netherrack", "furnace", "deepslate", "deepslate_iron_ore", "deepslate_gold_ore",
      "deepslate_diamond_ore", "deepslate_redstone_ore", "deepslate_emerald_ore",
      "deepslate_copper_ore", "deepslate_lapis_ore", "deepslate_coal_ore",
      "obsidian", "ancient_debris", "basalt", "blackstone", "end_stone",
      "nether_bricks", "prismarine", "terracotta", "diorite", "andesite", "granite",
    ]);
    const axeBlocks = new Set([
      "oak_log", "birch_log", "spruce_log", "jungle_log", "acacia_log",
      "dark_oak_log", "mangrove_log", "cherry_log", "crimson_stem", "warped_stem",
      "oak_planks", "birch_planks", "spruce_planks", "jungle_planks",
      "acacia_planks", "dark_oak_planks", "crafting_table", "chest", "bookshelf",
    ]);
    const shovelBlocks = new Set([
      "dirt", "grass_block", "sand", "gravel", "clay", "soul_sand", "soul_soil",
      "mycelium", "podzol", "farmland", "snow", "snow_block",
    ]);

    let toolType = null;
    if (pickaxeBlocks.has(blockName)) toolType = "pickaxe";
    else if (axeBlocks.has(blockName)) toolType = "axe";
    else if (shovelBlocks.has(blockName)) toolType = "shovel";
    if (!toolType) return null;

    const tiers = ["netherite", "diamond", "iron", "golden", "stone", "wooden"];
    const items = bot.inventory.items();
    for (const tier of tiers) {
      const tool = items.find((i) => i.name === `${tier}_${toolType}`);
      if (tool) return tool;
    }
    return null;
  }

  async _autoEquip(blockName) {
    const bot = this._requireBot();
    const tool = this._bestToolFor(blockName);
    if (tool) {
      try { await bot.equip(tool, "hand"); } catch (_) { /* ignore */ }
    }
  }

  async _collectNearbyDrops(radius = 4, maxItems = 3) {
    const bot = this._requireBot();
    const items = Object.values(bot.entities).filter(
      (e) => (e.name === "item" || e.displayName === "Item") &&
             bot.entity.position.distanceTo(e.position) <= radius
    );
    let collected = 0;
    for (const entity of items.slice(0, maxItems)) {
      try {
        await this.moveTo({
          x: Math.floor(entity.position.x),
          y: Math.floor(entity.position.y),
          z: Math.floor(entity.position.z),
          range: 1,
          timeout_ms: 3000,
        });
        collected += 1;
      } catch (_) { break; }
    }
    return collected;
  }

  async inspectWorld({ radius = 16 } = {}) {
    const bot = this._requireBot();
    const blocks = bot.findBlocks({
      matching: (block) => block && block.name !== "air",
      maxDistance: radius,
      count: 24,
    });
    return {
      radius,
      position: {
        x: Math.floor(bot.entity.position.x),
        y: Math.floor(bot.entity.position.y),
        z: Math.floor(bot.entity.position.z),
      },
      visible_blocks: blocks.map((position) => {
        const block = bot.blockAt(position);
        return {
          name: block?.name || "unknown",
          x: position.x,
          y: position.y,
          z: position.z,
        };
      }),
      nearby_entities: this._nearbyEntities(),
      objectives: [
        "Gather wood and stone for tool upgrades",
        "Smelt iron for armor and pickaxe",
        "Prepare blaze rods and ender pearls",
      ],
    };
  }

  async moveTo({ x, y, z, range = 1, timeout_ms = 30000 }) {
    return this._withPathLock(async () => {
      const bot = this._requireBot();
      const { Movements, goals } = this.pathfinder;
      const movements = new Movements(bot);
      movements.canDig = true;
      const goal = new goals.GoalNear(x, y, z, range);
      bot.pathfinder.setMovements(movements);

      let timer;
      try {
        const operation = bot.pathfinder.goto(goal);
        const timeout = new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error(`Timed out moving to ${x},${y},${z}`)), timeout_ms);
        });
        await Promise.race([operation, timeout]);
      } catch (err) {
        bot.pathfinder.stop();
        throw err;
      } finally {
        clearTimeout(timer);
      }
      return this.status();
    });
  }

  async mineResource({ name, count = 1, max_distance = 32 }) {
    const bot = this._requireBot();
    const blockInfo = this.registry.blocksByName[name];
    if (!blockInfo) {
      throw new Error(`Unknown block name: ${name}`);
    }

    await this._autoEat();

    let mined = 0;
    while (mined < count) {
      this._checkStopped();
      const target = bot.findBlock({ matching: blockInfo.id, maxDistance: max_distance });
      if (!target) break;

      const bx = target.position.x;
      const by = target.position.y;
      const bz = target.position.z;

      await this.moveTo({ x: bx, y: by, z: bz, range: 2, timeout_ms: 30000 });

      const freshBlock = bot.blockAt(new Vec3(bx, by, bz));
      if (!freshBlock || freshBlock.name === "air") continue;

      await this._autoEquip(name);
      try {
        await bot.dig(freshBlock, true);
        mined += 1;
      } catch (err) {
        const msg = (err.message || "").toLowerCase();
        if (msg.includes("not diggable") || msg.includes("air")) continue;
        throw err;
      }
    }

    await this._collectNearbyDrops();

    return {
      action: "mine_resource",
      resource: name,
      mined,
      ...this._context(),
    };
  }

  async craftItems({ item, count = 1 }) {
    const bot = this._requireBot();
    const itemInfo = this.registry.itemsByName[item];
    if (!itemInfo) {
      throw new Error(`Unknown item name: ${item}`);
    }

    const craftingTableBlock = this.registry.blocksByName.crafting_table;
    const table = craftingTableBlock
      ? bot.findBlock({ matching: craftingTableBlock.id, maxDistance: 6 })
      : null;
    const recipes = bot.recipesFor(itemInfo.id, null, 1, table || null);
    if (!recipes || recipes.length === 0) {
      throw new Error(`No available recipe for ${item}. Make sure a crafting table is placed nearby if this is a complex recipe.`);
    }

    const recipe = recipes[0];
    const outputPerCraft = recipe.result?.count ?? 1;
    const timesToCraft = Math.ceil(count / outputPerCraft);

    await bot.craft(recipe, timesToCraft, table || null);
    return {
      action: "craft_items",
      item,
      crafted: timesToCraft * outputPerCraft,
      ...this._context(),
    };
  }

  async placeBlock({ block, x, y, z }) {
    const bot = this._requireBot();
    const inventoryItem = bot.inventory.items().find((itemInfo) => itemInfo.name === block);
    if (!inventoryItem) {
      throw new Error(`Item ${block} is not in inventory.`);
    }

    await bot.equip(inventoryItem, "hand");
    await this.moveTo({ x, y, z, range: 4, timeout_ms: 15000 });

    const target = new Vec3(x, y, z);
    const existing = bot.blockAt(target);
    if (existing && existing.name !== "air") {
      return { action: "place_block", block, placed_at: { x, y, z }, note: "already_solid", ...this._context() };
    }

    // prefer below reference (gravity-safe), then sides
    const directions = [
      new Vec3(0, -1, 0),
      new Vec3(0, 1, 0),
      new Vec3(1, 0, 0),
      new Vec3(-1, 0, 0),
      new Vec3(0, 0, 1),
      new Vec3(0, 0, -1),
    ];

    let reference = null;
    let face = null;
    for (const direction of directions) {
      const neighbour = bot.blockAt(target.minus(direction));
      if (neighbour && neighbour.name !== "air") {
        reference = neighbour;
        face = direction;
        break;
      }
    }

    if (!reference || !face) {
      throw new Error(`No reference block adjacent to (${x},${y},${z}).`);
    }

    await bot.lookAt(reference.position.offset(0.5, 0.5, 0.5));
    await bot.placeBlock(reference, face);

    return {
      action: "place_block",
      block,
      placed_at: { x, y, z },
      ...this._context(),
    };
  }

  async digBlock({ x, y, z }) {
    const bot = this._requireBot();
    const block = bot.blockAt(new Vec3(x, y, z));
    if (!block || block.name === "air") {
      throw new Error(`No diggable block at ${x},${y},${z}.`);
    }
    const blockName = block.name;
    await this.moveTo({ x, y, z, range: 2, timeout_ms: 30000 });
    const fresh = bot.blockAt(new Vec3(x, y, z));
    if (!fresh || fresh.name === "air") {
      throw new Error(`Block at ${x},${y},${z} is already gone.`);
    }
    await this._autoEquip(fresh.name);
    await bot.dig(fresh, true);
    return {
      action: "dig_block",
      block: blockName,
      dug_at: { x, y, z },
      ...this._context(),
    };
  }

  _findNearestPlayer(bot, lowerName) {
    let target = null;
    let bestDist = Infinity;
    for (const entity of Object.values(bot.entities)) {
      if (entity === bot.entity || entity.type !== "player") continue;
      const pName = (entity.username || entity.name || "").toLowerCase();
      if (lowerName && pName === lowerName) return entity;
      const d = bot.entity.position.distanceTo(entity.position);
      if (d < bestDist) { bestDist = d; target = entity; }
    }
    if (!target && !lowerName) {
      for (const [username, pd] of Object.entries(bot.players)) {
        if (username === bot.username || !pd.entity) continue;
        const d = bot.entity.position.distanceTo(pd.entity.position);
        if (d < bestDist) { bestDist = d; target = pd.entity; }
      }
    }
    return target;
  }

  _findEntity(bot, lowerName, isAuto) {
    const NON_MOB_TYPES = new Set(["object", "orb", "other", "global"]);
    return bot.nearestEntity((candidate) => {
      if (candidate === bot.entity) return false;
      if (isAuto) {
        if (candidate.type === "player") return false;
        if (NON_MOB_TYPES.has(candidate.type)) return false;
        return true;
      }
      const names = [candidate.username, candidate.name, candidate.type].filter(Boolean);
      return names.some((n) => n.toLowerCase() === lowerName);
    });
  }

  async _moveToEntity(bot, entity, maxRetries = 3) {
    for (let retry = 0; retry < maxRetries; retry += 1) {
      try {
        await this.moveTo({
          x: Math.floor(entity.position.x),
          y: Math.floor(entity.position.y),
          z: Math.floor(entity.position.z),
          range: 2,
          timeout_ms: 15000,
        });
        return;
      } catch (err) {
        const msg = (err.message || "").toLowerCase();
        const isPathChange = msg.includes("changed") || msg.includes("path") || msg.includes("goal");
        if (!isPathChange || retry === maxRetries - 1) throw err;
      }
    }
  }

  async _equipBestSword(bot) {
    const swords = bot.inventory.items().filter((i) => i.name.endsWith("_sword"));
    if (swords.length === 0) return;
    const tiers = ["netherite", "diamond", "iron", "golden", "stone", "wooden"];
    const best = tiers.reduce((found, tier) => found || swords.find((s) => s.name.startsWith(tier)), null) || swords[0];
    try { await bot.equip(best, "hand"); } catch (_) { /* ignore */ }
  }

  async _fightUntilDead(bot, targetId, { tickMs = 200, maxTicks = 150 } = {}) {
    let hits = 0;

    for (let tick = 0; tick < maxTicks; tick++) {
      if (this._stopped) { this._stopped = false; bot.clearControlStates(); return { died: false, hits }; }
      const entity = bot.entities[targetId];
      if (!entity) return { died: true, hits };

      const dist = bot.entity.position.distanceTo(entity.position);

      if (dist > 10) {
        try {
          await this._moveToEntity(bot, entity, 1);
        } catch (_) { /* keep trying */ }
      } else if (dist > 3.5) {
        try {
          await bot.lookAt(entity.position.offset(0, entity.height * 0.85, 0));
          bot.setControlState("forward", true);
          bot.setControlState("sprint", true);
        } catch (_) { /* ignore */ }
      } else {
        bot.clearControlStates();
      }

      if (dist <= 6) {
        try {
          await bot.lookAt(entity.position.offset(0, entity.height * 0.85, 0));
          await bot.attack(entity);
          hits++;
        } catch (_) {
          if (!bot.entities[targetId]) return { died: true, hits };
        }
      }

      await new Promise((r) => setTimeout(r, tickMs));
    }

    bot.clearControlStates();
    const entity = bot.entities[targetId];
    return { died: !entity, hits };
  }

  async attackEntity({ name = "", count = 1 }) {
    const bot = this._requireBot();
    const lowerName = (name || "").toLowerCase().trim();
    const isAuto = !lowerName;

    await this._autoEat();
    await this._equipBestSword(bot);

    let kills = 0;
    let totalHits = 0;
    let targetName = name || "unknown";

    for (let killIdx = 0; killIdx < count; killIdx++) {
      this._checkStopped();
      const entity = this._findEntity(bot, lowerName, isAuto);
      if (!entity) break;

      if (killIdx === 0) {
        targetName = entity.name || entity.username || entity.type || targetName;
      }

      try { await this._moveToEntity(bot, entity, 1); } catch (_) { /* start fighting anyway */ }

      const result = await this._fightUntilDead(bot, entity.id);
      totalHits += result.hits;
      if (result.died) kills++;
    }

    bot.clearControlStates();

    if (kills === 0 && totalHits === 0) {
      const hint = isAuto ? "No mobs found nearby." : `No entity named '${name}' found nearby.`;
      throw new Error(hint);
    }

    await this._collectNearbyDrops();

    return {
      action: "attack_entity",
      target: targetName,
      killed: kills,
      hits: totalHits,
      ...this._context(),
    };
  }

  async findEntities({ radius = 32 } = {}) {
    const bot = this._requireBot();
    const entities = [];
    const botPos = bot.entity.position;

    for (const entity of Object.values(bot.entities)) {
      if (entity === bot.entity) continue;
      const dist = botPos.distanceTo(entity.position);
      if (dist > radius) continue;
      const name = entity.name || entity.username || entity.type;
      entities.push({
        name,
        kind: entity.type,
        distance: Math.floor(dist),
        x: Math.floor(entity.position.x),
        y: Math.floor(entity.position.y),
        z: Math.floor(entity.position.z),
        health: entity.health ?? null,
      });
    }

    entities.sort((a, b) => a.distance - b.distance);
    return { entities: entities.slice(0, 16), ...this._context() };
  }

  async sendChat({ message }) {
    const bot = this._requireBot();
    bot.chat(message);
    this._pushChat(bot.username, message, CHAT_TYPE_SELF);
    return {
      action: "send_chat",
      message,
      chat_messages: this.chatLog.slice(-10),
    };
  }

  async readChat({ limit = 20 }) {
    return {
      messages: this.chatLog.slice(-limit),
    };
  }

  async buildStructure(request) {
    const width = clampPositiveInt(request.width, 5);
    const length = clampPositiveInt(request.length, 5);
    const height = clampPositiveInt(request.height, 4);
    const steps = buildPlanFromPreset({
      preset: request.preset,
      material: request.material,
      originX: request.origin_x,
      originY: request.origin_y,
      originZ: request.origin_z,
      width,
      length,
      height,
    });
    let blocksPlaced = 0;
    for (const step of steps) {
      await this.placeBlock(step);
      blocksPlaced += 1;
    }
    return {
      action: "build_structure",
      preset: request.preset,
      material: request.material,
      blocks_placed: blocksPlaced,
      inventory: this._inventory(),
    };
  }

  async buildQuick({ shape, material = "", height, width, length, radius }) {
    const bot = this._requireBot();
    const pos = bot.entity.position;
    // Place 1 block away from bot in the direction they're facing
    const yaw = bot.entity.yaw;
    const ox = Math.floor(pos.x) + Math.round(-Math.sin(yaw) * 2);
    const oy = Math.floor(pos.y);
    const oz = Math.floor(pos.z) + Math.round(Math.cos(yaw) * 2);

    const s = shape.toLowerCase();
    const gen = getPreset(s);
    if (!gen) {
      throw new Error(
        `Unknown shape '${shape}'. Available: ${listPresets().join(", ")}`
      );
    }

    const isCreative = bot.game.gameMode === "creative";

    let block = material;
    if (!block) {
      if (isCreative) {
        const DEFAULTS = {
          house: "oak_planks", cabin: "oak_planks", cottage: "oak_planks",
          hut: "oak_planks", shelter: "cobblestone",
          wall: "cobblestone", stairs: "cobblestone", staircase: "cobblestone",
          watchtower: "cobblestone",
          bridge: "oak_planks", floor: "oak_planks", platform: "oak_planks",
          pillar: "stone", tower: "stone",
          fence: "oak_fence", enclosure: "oak_fence",
          farm: "farmland",
          pool: "stone_bricks",
          pyramid: "sandstone",
          arch: "stone_bricks",
          ring: "stone", circle: "stone",
        };
        block = DEFAULTS[s] || "oak_planks";
      } else {
        const inv = bot.inventory.items();
        const buildable = inv.filter((i) =>
          i.name.endsWith("_planks") || i.name === "cobblestone" || i.name === "stone" ||
          i.name === "dirt" || i.name.endsWith("_log") || i.name.endsWith("_bricks")
        );
        buildable.sort((a, b) => b.count - a.count);
        block = buildable.length > 0 ? buildable[0].name : null;
        if (!block) throw new Error("No building material in inventory. Mine some blocks first.");
      }
    }

    const opts = {};
    if (height != null) opts.height = Math.max(1, Math.min(height, 30));
    if (width  != null) opts.width  = Math.max(1, Math.min(width,  30));
    if (length != null) opts.length = Math.max(1, Math.min(length, 30));
    if (radius != null) opts.radius = Math.max(1, Math.min(radius, 15));
    opts.material = block;

    const placements = gen(ox, oy, oz, opts);

    if (!isCreative) {
      const inv = bot.inventory.items();
      const available = inv.filter((i) => i.name === block).reduce((sum, i) => sum + i.count, 0);
      if (available < placements.length) {
        placements.splice(available);
      }
    } else {
      const needed = Math.min(placements.length, 64);
      try {
        await bot.chat(`/give ${bot.username} ${block} ${needed}`);
        await new Promise((r) => setTimeout(r, 300));
      } catch (_) {}
    }

    let placed = 0;
    let skipped = 0;
    for (const p of placements) {
      if (this._stopped) { this._stopped = false; break; }
      try {
        await this.placeBlock({ block: p.block || block, x: p.x, y: p.y, z: p.z });
        placed++;
      } catch (_) {
        skipped++;
      }
    }

    return {
      action: "build_quick",
      shape: s,
      material: block,
      placed,
      skipped,
      total_planned: placements.length,
      ...this._context(),
    };
  }

  async getBlockAt({ x, y, z }) {
    const bot = this._requireBot();
    const block = bot.blockAt(new Vec3(x, y, z));
    return {
      action: "get_block_at",
      position: { x, y, z },
      name: block?.name ?? "air",
    };
  }

  async useBlock({ x, y, z }) {
    const bot = this._requireBot();
    const block = bot.blockAt(new Vec3(x, y, z));
    if (!block || block.name === "air") {
      throw new Error(`No block at ${x},${y},${z}.`);
    }
    await this.moveTo({ x, y, z, range: 4, timeout_ms: 15000 });
    await bot.activateBlock(block);
    return { action: "use_block", position: { x, y, z }, name: block.name };
  }

  async equipItem({ item, destination = "hand" }) {
    const bot = this._requireBot();
    const slot = bot.inventory.items().find((i) => i.name === item);
    if (!slot) {
      throw new Error(`Item ${item} not in inventory.`);
    }
    await bot.equip(slot, destination);
    return { action: "equip_item", item, destination, ...this._context() };
  }

  async dropItem({ item, count = 1 }) {
    const bot = this._requireBot();
    const slot = bot.inventory.items().find((i) => i.name === item);
    if (!slot) {
      throw new Error(`Item ${item} not in inventory.`);
    }
    const toDrop = Math.min(count, slot.count);
    await bot.toss(slot.type, null, toDrop);
    return { action: "drop_item", item, count: toDrop, ...this._context() };
  }

  async eat({ item }) {
    const bot = this._requireBot();
    const slot = bot.inventory.items().find((i) => i.name === item);
    if (!slot) {
      throw new Error(`Item ${item} not in inventory.`);
    }
    await bot.equip(slot, "hand");
    await bot.consume();
    return { action: "eat", item, ...this._context() };
  }

  async lookAt({ x, y, z }) {
    const bot = this._requireBot();
    const target = new Vec3(x, y, z);
    await bot.lookAt(target.offset(0.5, 0.5, 0.5));
    return { action: "look_at", position: { x, y, z } };
  }

  async jump() {
    const bot = this._requireBot();
    bot.setControlState("jump", true);
    await new Promise((r) => setTimeout(r, 250));
    bot.setControlState("jump", false);
    return { action: "jump" };
  }

  async setSprint({ sprint = true }) {
    const bot = this._requireBot();
    bot.setControlState("sprint", !!sprint);
    return { action: "set_sprint", sprint: !!sprint };
  }

  async setSneak({ sneak = true }) {
    const bot = this._requireBot();
    bot.setControlState("sneak", !!sneak);
    return { action: "set_sneak", sneak: !!sneak };
  }

  async sleep({ x, y, z }) {
    const bot = this._requireBot();
    let bed;
    if (x !== undefined && y !== undefined && z !== undefined) {
      const block = bot.blockAt(new Vec3(x, y, z));
      if (block && bot.isABed(block)) {
        bed = block;
      }
    }
    if (!bed) {
      bed = bot.findBlock({
        matching: (block) => bot.isABed(block),
        maxDistance: 8,
      });
    }
    if (!bed) {
      throw new Error("No bed found nearby.");
    }
    await this.moveTo({
      x: bed.position.x,
      y: bed.position.y,
      z: bed.position.z,
      range: 2,
      timeout_ms: 15000,
    });
    await bot.sleep(bed);
    return { action: "sleep", position: { x: bed.position.x, y: bed.position.y, z: bed.position.z } };
  }

  async wake() {
    const bot = this._requireBot();
    if (bot.isSleeping) {
      await bot.wake();
    }
    return { action: "wake" };
  }

  async collectItems({ radius = 8 } = {}) {
    const bot = this._requireBot();
    const items = Object.values(bot.entities)
      .filter((e) => (e.name === "item" || e.displayName === "Item") &&
        bot.entity.position.distanceTo(e.position) <= radius)
      .sort((a, b) => bot.entity.position.distanceTo(a.position) - bot.entity.position.distanceTo(b.position));
    let collected = 0;
    for (const entity of items) {
      if (this._stopped) { this._stopped = false; break; }
      try {
        await this.moveTo({
          x: Math.floor(entity.position.x),
          y: Math.floor(entity.position.y),
          z: Math.floor(entity.position.z),
          range: 1,
          timeout_ms: 5000,
        });
        collected += 1;
      } catch (_) { /* skip this item, try next */ }
    }
    return { action: "collect_items", collected, radius, ...this._context() };
  }

  async fish() {
    const bot = this._requireBot();
    const rod = bot.inventory.items().find((i) => i.name === "fishing_rod");
    if (!rod) {
      throw new Error("No fishing_rod in inventory.");
    }
    await bot.equip(rod, "hand");
    await bot.fish();
    return { action: "fish", ...this._context() };
  }

  async mountEntity({ name }) {
    const bot = this._requireBot();
    const lowerName = name.toLowerCase();
    const entity = this._findEntity(bot, lowerName, false);
    if (!entity) {
      throw new Error(`No entity named '${name}' found nearby.`);
    }
    await this._moveToEntity(bot, entity);
    await bot.mount(entity);
    return { action: "mount_entity", target: name };
  }

  async dismount() {
    const bot = this._requireBot();
    if (bot.vehicle) {
      bot.dismount();
    }
    return { action: "dismount" };
  }

  async interactEntity({ name }) {
    const bot = this._requireBot();
    const lowerName = name.toLowerCase();
    const entity = this._findEntity(bot, lowerName, false);
    if (!entity) {
      throw new Error(`No entity named '${name}' found nearby.`);
    }
    await this._moveToEntity(bot, entity);
    await bot.activateEntity(entity);
    return { action: "interact_entity", target: name };
  }

  async goToPlayer({ name, range = 2 }) {
    const bot = this._requireBot();
    const lowerName = (name || "").toLowerCase();
    let target = this._findNearestPlayer(bot, lowerName);

    if (!target) {
      throw new Error(`Player '${name}' not found nearby. Use find_players to check who is online.`);
    }

    const resolvedName = target.username || target.name || name;
    await this._moveToEntity(bot, target);
    return {
      action: "go_to_player",
      target: resolvedName,
      arrived_at: {
        x: Math.floor(target.position.x),
        y: Math.floor(target.position.y),
        z: Math.floor(target.position.z),
      },
      ...this._context(),
    };
  }

  async goToEntity({ name = "", range = 2 }) {
    const bot = this._requireBot();
    const lowerName = (name || "").toLowerCase().trim();
    const isAuto = !lowerName;
    const entity = this._findEntity(bot, lowerName, isAuto);

    if (!entity) {
      const hint = isAuto ? "No mobs found nearby." : `No entity named '${name}' found nearby. Use find_entities to check what's around.`;
      throw new Error(hint);
    }

    const targetName = entity.name || entity.username || entity.type || name;
    await this._moveToEntity(bot, entity);
    return {
      action: "go_to_entity",
      target: targetName,
      arrived_at: {
        x: Math.floor(entity.position.x),
        y: Math.floor(entity.position.y),
        z: Math.floor(entity.position.z),
      },
      ...this._context(),
    };
  }

  async hunt({ name = "", count = 5, radius = 48 }) {
    const bot = this._requireBot();
    const lowerName = (name || "").toLowerCase().trim();
    const isAuto = !lowerName;
    await this._autoEat();
    await this._equipBestSword(bot);

    let kills = 0;
    let totalHits = 0;
    const lootBefore = bot.inventory.items().reduce((s, i) => s + i.count, 0);

    for (let i = 0; i < count; i++) {
      if (this._stopped) { this._stopped = false; break; }
      const entity = isAuto
        ? bot.nearestEntity((e) => {
            if (e === bot.entity || e.type === "player") return false;
            const NON = new Set(["object", "orb", "other", "global"]);
            if (NON.has(e.type)) return false;
            return bot.entity.position.distanceTo(e.position) <= radius;
          })
        : bot.nearestEntity((e) => {
            if (e === bot.entity) return false;
            const n = (e.name || e.username || "").toLowerCase();
            return n === lowerName && bot.entity.position.distanceTo(e.position) <= radius;
          });
      if (!entity) break;

      try { await this._moveToEntity(bot, entity, 1); } catch (_) {}
      const result = await this._fightUntilDead(bot, entity.id);
      totalHits += result.hits;
      if (result.died) kills++;

      await this._collectNearbyDrops(6, 8);
      await this._autoEat();
    }

    bot.clearControlStates();
    const lootAfter = bot.inventory.items().reduce((s, i) => s + i.count, 0);

    return {
      action: "hunt",
      target: name || "any mob",
      killed: kills,
      hits: totalHits,
      items_collected: Math.max(0, lootAfter - lootBefore),
      ...this._context(),
    };
  }

  async gatherWood({ count = 16, type = "" }) {
    const bot = this._requireBot();
    await this._autoEat();

    const LOG_NAMES = [
      "oak_log", "birch_log", "spruce_log", "jungle_log",
      "acacia_log", "dark_oak_log", "mangrove_log", "cherry_log",
    ];
    const targetLogs = type
      ? LOG_NAMES.filter((l) => l.includes(type.toLowerCase()))
      : LOG_NAMES;
    if (targetLogs.length === 0) throw new Error(`Unknown wood type: ${type}`);

    const matchIds = new Set();
    for (const logName of targetLogs) {
      const blockInfo = this.registry.blocksByName[logName];
      if (blockInfo) matchIds.add(blockInfo.id);
    }
    if (matchIds.size === 0) throw new Error("No log block types found in registry.");

    let chopped = 0;
    while (chopped < count) {
      this._checkStopped();
      const target = bot.findBlock({
        matching: (block) => matchIds.has(block.type),
        maxDistance: 64,
      });
      if (!target) break;

      const bx = target.position.x;
      const by = target.position.y;
      const bz = target.position.z;

      await this.moveTo({ x: bx, y: by, z: bz, range: 2, timeout_ms: 30000 });
      const fresh = bot.blockAt(new Vec3(bx, by, bz));
      if (!fresh || fresh.name === "air") continue;

      await this._autoEquip(fresh.name);
      try {
        await bot.dig(fresh, true);
        chopped++;
      } catch (err) {
        const msg = (err.message || "").toLowerCase();
        if (msg.includes("not diggable") || msg.includes("air")) continue;
        throw err;
      }

      for (let dy = 1; dy <= 10; dy++) {
        const above = bot.blockAt(new Vec3(bx, by + dy, bz));
        if (!above || !LOG_NAMES.includes(above.name)) break;
        try {
          await this._autoEquip(above.name);
          await bot.dig(above, true);
          chopped++;
        } catch (_) { break; }
        if (chopped >= count) break;
      }
    }

    await this._collectNearbyDrops(8, 16);

    return {
      action: "gather_wood",
      type: type || "any",
      chopped,
      ...this._context(),
    };
  }

  async clearArea({ radius = 3, depth = 1 }) {
    const bot = this._requireBot();
    const pos = bot.entity.position;
    const cx = Math.floor(pos.x);
    const cy = Math.floor(pos.y);
    const cz = Math.floor(pos.z);
    const r = Math.max(1, Math.min(radius, 8));
    const d = Math.max(1, Math.min(depth, 5));

    let cleared = 0;
    for (let y = cy + d - 1; y >= cy; y--)
      for (let x = cx - r; x <= cx + r; x++)
        for (let z = cz - r; z <= cz + r; z++) {
          if (this._stopped) { this._stopped = false; return { action: "clear_area", radius: r, depth: d, cleared, stopped: true, ...this._context() }; }
          const block = bot.blockAt(new Vec3(x, y, z));
          if (!block || block.name === "air" || block.name === "bedrock") continue;
          try {
            await this._autoEquip(block.name);
            await this.moveTo({ x, y, z, range: 3, timeout_ms: 10000 });
            const fresh = bot.blockAt(new Vec3(x, y, z));
            if (fresh && fresh.name !== "air") {
              await bot.dig(fresh, true);
              cleared++;
            }
          } catch (_) { /* skip */ }
        }

    await this._collectNearbyDrops(r + 2, 32);
    return { action: "clear_area", radius: r, depth: d, cleared, ...this._context() };
  }

  async followPlayer({ name, duration_seconds = 30 }) {
    const bot = this._requireBot();
    const lowerName = (name || "").toLowerCase();
    const cappedDuration = Math.min(duration_seconds, 60);
    const endTime = Date.now() + cappedDuration * 1000;
    let steps = 0;
    let resolvedName = name;

    while (Date.now() < endTime) {
      if (this._stopped) { this._stopped = false; break; }

      const target = this._findNearestPlayer(bot, lowerName);
      if (!target) {
        await new Promise((r) => setTimeout(r, 1000));
        continue;
      }
      if (steps === 0) resolvedName = target.username || target.name || name;

      const dist = bot.entity.position.distanceTo(target.position);
      if (dist > 3) {
        try {
          await this.moveTo({
            x: Math.floor(target.position.x),
            y: Math.floor(target.position.y),
            z: Math.floor(target.position.z),
            range: 2,
            timeout_ms: 5000,
          });
          steps++;
        } catch (_) { /* retry next tick */ }
      } else {
        await new Promise((r) => setTimeout(r, 500));
      }
    }

    bot.clearControlStates();
    return { action: "follow_player", target: resolvedName, duration_seconds: cappedDuration, steps, ...this._context() };
  }

  async defendArea({ radius = 10, duration_seconds = 60 }) {
    const bot = this._requireBot();
    await this._autoEat();
    await this._equipBestSword(bot);

    const homePos = bot.entity.position.clone();
    const cappedDuration = Math.min(duration_seconds, 120);
    const endTime = Date.now() + cappedDuration * 1000;
    const HOSTILE = new Set([
      "zombie", "skeleton", "creeper", "spider", "enderman", "witch",
      "phantom", "drowned", "husk", "stray", "pillager", "vindicator",
      "ravager", "vex", "evoker", "blaze", "ghast", "wither_skeleton",
      "piglin_brute", "hoglin", "zoglin", "warden", "slime", "magma_cube",
      "cave_spider", "silverfish", "endermite", "zombie_villager",
    ]);
    let kills = 0;

    while (Date.now() < endTime) {
      if (this._stopped) { this._stopped = false; break; }

      const hostile = bot.nearestEntity((e) => {
        if (e === bot.entity) return false;
        const n = (e.name || "").toLowerCase();
        return HOSTILE.has(n) && bot.entity.position.distanceTo(e.position) <= radius;
      });

      if (hostile) {
        try { await this._moveToEntity(bot, hostile, 1); } catch (_) {}
        const result = await this._fightUntilDead(bot, hostile.id);
        if (result.died) kills++;
        await this._collectNearbyDrops(6, 8);
        await this._autoEat();

        const distFromHome = bot.entity.position.distanceTo(homePos);
        if (distFromHome > 5) {
          try {
            await this.moveTo({ x: Math.floor(homePos.x), y: Math.floor(homePos.y), z: Math.floor(homePos.z), range: 2, timeout_ms: 10000 });
          } catch (_) {}
        }
      } else {
        await new Promise((r) => setTimeout(r, 1000));
      }
    }

    bot.clearControlStates();
    return { action: "defend_area", radius, duration_seconds, kills, ...this._context() };
  }

  async storeItems({ item = "", chest_x, chest_y, chest_z }) {
    const bot = this._requireBot();
    let chestPos;

    if (chest_x != null && chest_y != null && chest_z != null) {
      chestPos = bot.blockAt(new Vec3(chest_x, chest_y, chest_z));
    } else {
      const chestBlockInfo = this.registry.blocksByName.chest;
      chestPos = chestBlockInfo
        ? bot.findBlock({ matching: chestBlockInfo.id, maxDistance: 8 })
        : null;
    }
    if (!chestPos) throw new Error("No chest found nearby. Place a chest first.");

    await this.moveTo({
      x: chestPos.position.x, y: chestPos.position.y, z: chestPos.position.z,
      range: 3, timeout_ms: 15000,
    });

    const chest = await bot.openContainer(chestPos);
    let stored = 0;
    try {
      const items = bot.inventory.items();
      const toStore = item
        ? items.filter((i) => i.name === item.toLowerCase())
        : items;
      for (const slot of toStore) {
        try {
          await chest.deposit(slot.type, null, slot.count);
          stored += slot.count;
        } catch (_) { /* chest full or item issue */ }
      }
    } finally {
      chest.close();
    }

    return { action: "store_items", stored, ...this._context() };
  }

  async retrieveItems({ item, count = 64, chest_x, chest_y, chest_z }) {
    const bot = this._requireBot();
    let chestPos;

    if (chest_x != null && chest_y != null && chest_z != null) {
      chestPos = bot.blockAt(new Vec3(chest_x, chest_y, chest_z));
    } else {
      const chestBlockInfo = this.registry.blocksByName.chest;
      chestPos = chestBlockInfo
        ? bot.findBlock({ matching: chestBlockInfo.id, maxDistance: 8 })
        : null;
    }
    if (!chestPos) throw new Error("No chest found nearby.");

    await this.moveTo({
      x: chestPos.position.x, y: chestPos.position.y, z: chestPos.position.z,
      range: 3, timeout_ms: 15000,
    });

    const chest = await bot.openContainer(chestPos);
    let retrieved = 0;
    try {
      const chestItems = chest.containerItems();
      const target = chestItems.find((i) => i.name === item.toLowerCase());
      if (target) {
        const toTake = Math.min(count, target.count);
        await chest.withdraw(target.type, null, toTake);
        retrieved = toTake;
      }
    } finally {
      chest.close();
    }

    return { action: "retrieve_items", item, retrieved, ...this._context() };
  }

  async plantCrops({ seed = "wheat_seeds", rows = 3, cols = 3 }) {
    const bot = this._requireBot();
    const pos = bot.entity.position;
    const ox = Math.floor(pos.x) + 1;
    const oy = Math.floor(pos.y);
    const oz = Math.floor(pos.z) + 1;

    const seedItem = bot.inventory.items().find((i) => i.name === seed);
    if (!seedItem) throw new Error(`No ${seed} in inventory.`);

    let planted = 0;
    for (let x = 0; x < rows; x++)
      for (let z = 0; z < cols; z++) {
        const bx = ox + x;
        const bz = oz + z;
        const below = bot.blockAt(new Vec3(bx, oy - 1, bz));
        if (!below || (below.name !== "farmland" && below.name !== "dirt" && below.name !== "grass_block")) continue;

        // hoe dirt/grass into farmland
        if (below.name === "dirt" || below.name === "grass_block") {
          const hoe = bot.inventory.items().find((i) => i.name.endsWith("_hoe"));
          if (hoe) {
            try {
              await bot.equip(hoe, "hand");
              await this.moveTo({ x: bx, y: oy, z: bz, range: 3, timeout_ms: 5000 });
              await bot.activateBlock(below);
            } catch (_) { continue; }
          } else continue;
        }

        try {
          const freshSeed = bot.inventory.items().find((i) => i.name === seed);
          if (!freshSeed) break;
          await bot.equip(freshSeed, "hand");
          await this.moveTo({ x: bx, y: oy, z: bz, range: 3, timeout_ms: 5000 });
          const farmBlock = bot.blockAt(new Vec3(bx, oy - 1, bz));
          if (farmBlock) {
            await bot.placeBlock(farmBlock, new Vec3(0, 1, 0));
            planted++;
          }
        } catch (_) { /* skip */ }
      }

    return { action: "plant_crops", seed, planted, area: `${rows}x${cols}`, ...this._context() };
  }

  async harvestCrops({ radius = 6 }) {
    const bot = this._requireBot();
    const CROPS = new Set(["wheat", "carrots", "potatoes", "beetroots", "nether_wart"]);
    const pos = bot.entity.position;
    let harvested = 0;

    const blocks = bot.findBlocks({
      matching: (block) => block && CROPS.has(block.name),
      maxDistance: radius,
      count: 100,
    });

    for (const bpos of blocks) {
      if (this._stopped) { this._stopped = false; break; }
      const block = bot.blockAt(bpos);
      if (!block) continue;
      // only harvest mature crops (metadata >= 7 for most crops)
      const age = block.metadata;
      if (block.name === "beetroots" || block.name === "nether_wart") {
        if (age < 3) continue;
      } else {
        if (age < 7) continue;
      }

      try {
        await this.moveTo({ x: bpos.x, y: bpos.y, z: bpos.z, range: 3, timeout_ms: 5000 });
        const fresh = bot.blockAt(bpos);
        if (fresh && CROPS.has(fresh.name)) {
          await bot.dig(fresh, true);
          harvested++;
        }
      } catch (_) { /* skip */ }
    }

    await this._collectNearbyDrops(radius + 2, 32);
    return { action: "harvest_crops", harvested, radius, ...this._context() };
  }

  async makeTools({ material = "" }) {
    const bot = this._requireBot();

    const _refreshInv = () => {
      const m = {};
      for (const i of bot.inventory.items()) m[i.name] = (m[i.name] || 0) + i.count;
      return m;
    };

    const _craft = async (itemName, count, table) => {
      const info = this.registry.itemsByName[itemName];
      if (!info) return false;
      const recipes = bot.recipesFor(info.id, null, 1, table || null);
      if (!recipes || recipes.length === 0) return false;
      await bot.craft(recipes[0], count, table || null);
      return true;
    };

    let invMap = _refreshInv();

    // Auto-craft planks from any logs if we lack planks
    const LOG_NAMES = [
      "oak_log", "birch_log", "spruce_log", "jungle_log",
      "acacia_log", "dark_oak_log", "mangrove_log", "cherry_log",
      "crimson_stem", "warped_stem",
    ];
    const PLANK_NAMES = [
      "oak_planks", "birch_planks", "spruce_planks", "jungle_planks",
      "acacia_planks", "dark_oak_planks", "mangrove_planks", "cherry_planks",
      "crimson_planks", "warped_planks",
    ];
    const totalPlanks = PLANK_NAMES.reduce((s, p) => s + (invMap[p] || 0), 0);
    if (totalPlanks < 8) {
      for (const logName of LOG_NAMES) {
        if ((invMap[logName] || 0) >= 1) {
          const plankName = logName.replace(/_log$/, "_planks").replace(/_stem$/, "_planks");
          const logsToConvert = Math.min(invMap[logName], 4);
          try { await _craft(plankName, logsToConvert, null); } catch (_) {}
          break;
        }
      }
      invMap = _refreshInv();
    }

    // Auto-craft sticks if we lack them
    if ((invMap["stick"] || 0) < 4) {
      const anyPlank = PLANK_NAMES.find((p) => (invMap[p] || 0) >= 2);
      if (anyPlank) {
        try { await _craft("stick", 2, null); } catch (_) {}
        invMap = _refreshInv();
      }
    }

    const TIERS = [
      { name: "diamond", ingot: "diamond" },
      { name: "iron", ingot: "iron_ingot" },
      { name: "stone", ingot: "cobblestone" },
      { name: "wooden", ingot: "oak_planks" },
    ];

    const targetTier = material
      ? TIERS.find((t) => t.name === material.toLowerCase())
      : TIERS.find((t) => (invMap[t.ingot] || 0) >= 3);

    if (!targetTier) {
      const logs = LOG_NAMES.reduce((s, l) => s + (invMap[l] || 0), 0);
      if (logs > 0) {
        throw new Error(
          `Have ${logs} logs but need planks. Logs were auto-converted — retry make_tools.`
        );
      }
      throw new Error("No suitable materials for tools. Gather wood or mine cobblestone first.");
    }

    // Auto-place crafting table if none nearby
    const craftingTableBlock = this.registry.blocksByName.crafting_table;
    let table = craftingTableBlock
      ? bot.findBlock({ matching: craftingTableBlock.id, maxDistance: 6 })
      : null;

    if (!table && (invMap["crafting_table"] || 0) > 0) {
      const pos = bot.entity.position;
      const placeX = Math.floor(pos.x) + 1;
      const placeY = Math.floor(pos.y);
      const placeZ = Math.floor(pos.z);
      try {
        await this.placeBlock({ block: "crafting_table", x: placeX, y: placeY, z: placeZ });
        table = bot.blockAt(new Vec3(placeX, placeY, placeZ));
      } catch (_) {}
    }

    if (!table && (invMap["crafting_table"] || 0) === 0) {
      const anyPlank = PLANK_NAMES.find((p) => (invMap[p] || 0) >= 4);
      if (anyPlank) {
        try {
          await _craft("crafting_table", 1, null);
          invMap = _refreshInv();
          const pos = bot.entity.position;
          const placeX = Math.floor(pos.x) + 1;
          const placeY = Math.floor(pos.y);
          const placeZ = Math.floor(pos.z);
          await this.placeBlock({ block: "crafting_table", x: placeX, y: placeY, z: placeZ });
          table = bot.blockAt(new Vec3(placeX, placeY, placeZ));
        } catch (_) {}
      }
    }

    const TOOLS = ["pickaxe", "axe", "sword", "shovel"];
    const crafted = [];

    for (const toolType of TOOLS) {
      const toolName = `${targetTier.name}_${toolType}`;
      const already = bot.inventory.items().find((i) => i.name === toolName);
      if (already) continue;

      try {
        const ok = await _craft(toolName, 1, table);
        if (ok) crafted.push(toolName);
      } catch (_) {}
    }

    return { action: "make_tools", material: targetTier.name, crafted, ...this._context() };
  }

  async smeltAll({ item, fuel = "coal" }) {
    const bot = this._requireBot();
    const furnaceBlock = this.registry.blocksByName.furnace;
    if (!furnaceBlock) throw new Error("Furnace block not in registry.");
    const furnacePos = bot.findBlock({ matching: furnaceBlock.id, maxDistance: 6 });
    if (!furnacePos) throw new Error("No furnace nearby. Place a furnace first.");

    await this.moveTo({
      x: furnacePos.position.x, y: furnacePos.position.y, z: furnacePos.position.z,
      range: 3, timeout_ms: 15000,
    });

    const inputItem = bot.inventory.items().find((i) => i.name === item);
    if (!inputItem) throw new Error(`${item} not in inventory.`);

    const fuelItem = bot.inventory.items().find((i) => i.name === fuel);
    if (!fuelItem) throw new Error(`${fuel} (fuel) not in inventory.`);

    const toSmelt = inputItem.count;
    const furnace = await bot.openFurnace(furnacePos);
    try {
      await furnace.putFuel(fuelItem.type, null, Math.ceil(toSmelt / 8));
      await furnace.putInput(inputItem.type, null, toSmelt);
      const waitMs = Math.min(toSmelt * 10000 + 2000, 120000);
      await new Promise((r) => setTimeout(r, waitMs));
      await furnace.takeOutput();
    } finally {
      furnace.close();
    }

    return { action: "smelt_all", input: item, smelted: toSmelt, fuel, ...this._context() };
  }

  async stopMovement() {
    this._stopped = true;
    try {
      const bot = this._requireBot();
      if (bot.pathfinder) bot.pathfinder.stop();
      bot.clearControlStates();
    } catch (_) {}
    return { action: "stop_movement" };
  }

  async findPlayers() {
    const bot = this._requireBot();
    const seen = new Set();
    const players = [];

    for (const entity of Object.values(bot.entities)) {
      if (entity === bot.entity) continue;
      if (entity.type !== "player") continue;
      const name = entity.username || entity.name || "unknown";
      seen.add(name);
      players.push({
        name,
        x: Math.floor(entity.position.x),
        y: Math.floor(entity.position.y),
        z: Math.floor(entity.position.z),
        distance: Math.floor(bot.entity.position.distanceTo(entity.position)),
        health: entity.health ?? entity.metadata?.[9] ?? null,
      });
    }

    for (const [username, playerData] of Object.entries(bot.players)) {
      if (username === bot.username) continue;
      if (seen.has(username)) continue;
      const entry = { name: username, x: null, y: null, z: null, distance: null, health: null };
      if (playerData.entity && playerData.entity.position) {
        entry.x = Math.floor(playerData.entity.position.x);
        entry.y = Math.floor(playerData.entity.position.y);
        entry.z = Math.floor(playerData.entity.position.z);
        entry.distance = Math.floor(bot.entity.position.distanceTo(playerData.entity.position));
        entry.health = playerData.entity.health ?? playerData.entity.metadata?.[9] ?? null;
      }
      players.push(entry);
    }

    return { players };
  }

  async smeltItem({ item, count = 1, fuel = "coal" }) {
    const bot = this._requireBot();

    const furnaceBlock = this.registry.blocksByName.furnace;
    if (!furnaceBlock) {
      throw new Error("Furnace block type not found in registry.");
    }
    const furnacePos = bot.findBlock({ matching: furnaceBlock.id, maxDistance: 6 });
    if (!furnacePos) {
      throw new Error("No furnace within range. Place a furnace first.");
    }

    await this.moveTo({
      x: furnacePos.position.x,
      y: furnacePos.position.y,
      z: furnacePos.position.z,
      range: 3,
      timeout_ms: 15000,
    });

    const furnace = await bot.openFurnace(furnacePos);
    try {
      const inputItem = bot.inventory.items().find((i) => i.name === item);
      if (!inputItem) {
        throw new Error(`${item} not in inventory.`);
      }
      const fuelItem = bot.inventory.items().find((i) => i.name === fuel);
      if (!fuelItem) {
        throw new Error(`${fuel} (fuel) not in inventory.`);
      }

      const toSmelt = Math.min(count, inputItem.count);
      await furnace.putFuel(fuelItem.type, null, Math.ceil(toSmelt / 8));
      await furnace.putInput(inputItem.type, null, toSmelt);

      const waitMs = toSmelt * 10000 + 2000;
      await new Promise((r) => setTimeout(r, Math.min(waitMs, 120000)));

      await furnace.takeOutput();
    } finally {
      furnace.close();
    }

    return {
      action: "smelt_item",
      input: item,
      count,
      fuel,
      ...this._context(),
    };
  }

  async runCommand({ command }) {
    const bot = this._requireBot();
    bot.chat(command);
    this._pushChat(bot.username, command, CHAT_TYPE_SELF);
    await new Promise((r) => setTimeout(r, 500));
    return {
      action: "run_command",
      command,
      chat_messages: this.chatLog.slice(-5),
    };
  }

  async buildBlueprint({ blocks }) {
    let placed = 0;
    for (const entry of blocks) {
      try {
        await this.placeBlock({ block: entry.block, x: entry.x, y: entry.y, z: entry.z });
        placed += 1;
      } catch (_) {
        // skip blocks that fail to place
      }
    }
    return {
      action: "build_blueprint",
      blocks_placed: placed,
      blocks_requested: blocks.length,
      ...this._context(),
    };
  }
}


async function main() {
  const config = parseArgs(process.argv.slice(2));
  const session = config.simulate ? new SimulationSession() : new MineflayerSession();

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://localhost");
      const body = req.method === "POST" ? await parseBody(req) : {};

      if (req.method === "GET" && url.pathname === "/health") {
        jsonResponse(res, 200, {
          ok: true,
          result: {
            mode: config.simulate ? "simulate" : "real",
          },
        });
        return;
      }

      if (req.method === "POST" && url.pathname === "/session/connect") {
        jsonResponse(res, 200, { ok: true, result: await session.connect(body) });
        return;
      }

      if (req.method === "POST" && url.pathname === "/session/disconnect") {
        jsonResponse(res, 200, { ok: true, result: await session.disconnect() });
        return;
      }

      if (req.method === "GET" && url.pathname === "/session/status") {
        jsonResponse(res, 200, { ok: true, result: await session.status() });
        return;
      }

      if (req.method === "GET" && url.pathname === "/world/snapshot") {
        jsonResponse(res, 200, {
          ok: true,
          result: await session.inspectWorld({
            radius: clampPositiveInt(url.searchParams.get("radius"), 16),
          }),
        });
        return;
      }

      if (req.method === "GET" && url.pathname === "/players") {
        jsonResponse(res, 200, { ok: true, result: await session.findPlayers() });
        return;
      }

      if (req.method === "GET" && url.pathname === "/entities") {
        jsonResponse(res, 200, {
          ok: true,
          result: await session.findEntities({
            radius: clampPositiveInt(url.searchParams.get("radius"), 32),
          }),
        });
        return;
      }

      if (req.method === "GET" && url.pathname === "/chat/messages") {
        jsonResponse(res, 200, {
          ok: true,
          result: await session.readChat({
            limit: clampPositiveInt(url.searchParams.get("limit"), 20),
          }),
        });
        return;
      }

      const routes = {
        "/actions/move_to": (payload) => session.moveTo(payload),
        "/actions/mine_resource": (payload) => session.mineResource(payload),
        "/actions/craft_items": (payload) => session.craftItems(payload),
        "/actions/place_block": (payload) => session.placeBlock(payload),
        "/actions/dig_block": (payload) => session.digBlock(payload),
        "/actions/attack_entity": (payload) => session.attackEntity(payload),
        "/actions/go_to_player": (payload) => session.goToPlayer(payload),
        "/actions/go_to_entity": (payload) => session.goToEntity(payload),
        "/actions/send_chat": (payload) => session.sendChat(payload),
        "/actions/build_structure": (payload) => session.buildStructure(payload),
        "/actions/build_quick": (payload) => session.buildQuick(payload),
        "/actions/get_block_at": (payload) => session.getBlockAt(payload),
        "/actions/use_block": (payload) => session.useBlock(payload),
        "/actions/equip_item": (payload) => session.equipItem(payload),
        "/actions/drop_item": (payload) => session.dropItem(payload),
        "/actions/eat": (payload) => session.eat(payload),
        "/actions/look_at": (payload) => session.lookAt(payload),
        "/actions/jump": (payload) => session.jump(payload),
        "/actions/set_sprint": (payload) => session.setSprint(payload),
        "/actions/set_sneak": (payload) => session.setSneak(payload),
        "/actions/sleep": (payload) => session.sleep(payload),
        "/actions/wake": (payload) => session.wake(payload),
        "/actions/collect_items": (payload) => session.collectItems(payload),
        "/actions/fish": (payload) => session.fish(payload),
        "/actions/mount_entity": (payload) => session.mountEntity(payload),
        "/actions/dismount": (payload) => session.dismount(payload),
        "/actions/interact_entity": (payload) => session.interactEntity(payload),
        "/actions/stop_movement": (payload) => session.stopMovement(payload),
        "/actions/smelt_item": (payload) => session.smeltItem(payload),
        "/actions/smelt_all": (payload) => session.smeltAll(payload),
        "/actions/run_command": (payload) => session.runCommand(payload),
        "/actions/build_blueprint": (payload) => session.buildBlueprint(payload),
        "/actions/hunt": (payload) => session.hunt(payload),
        "/actions/gather_wood": (payload) => session.gatherWood(payload),
        "/actions/clear_area": (payload) => session.clearArea(payload),
        "/actions/follow_player": (payload) => session.followPlayer(payload),
        "/actions/defend_area": (payload) => session.defendArea(payload),
        "/actions/store_items": (payload) => session.storeItems(payload),
        "/actions/retrieve_items": (payload) => session.retrieveItems(payload),
        "/actions/plant_crops": (payload) => session.plantCrops(payload),
        "/actions/harvest_crops": (payload) => session.harvestCrops(payload),
        "/actions/make_tools": (payload) => session.makeTools(payload),
      };

      if (req.method === "POST" && routes[url.pathname]) {
        jsonResponse(res, 200, { ok: true, result: await routes[url.pathname](body) });
        return;
      }

      jsonResponse(res, 404, {
        ok: false,
        error: `Route not found: ${req.method} ${url.pathname}`,
      });
    } catch (error) {
      jsonResponse(res, 500, {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  });

  server.listen(config.port, config.host, () => {
    console.log(
      `[minecraft-dedalus-bridge] listening on http://${config.host}:${config.port} (${config.simulate ? "simulate" : "real"} mode)`,
    );
  });
}


main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
