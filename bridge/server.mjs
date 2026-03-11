import http from "node:http";
import { once } from "node:events";
import { URL } from "node:url";

import { Vec3 } from "vec3";


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
  const steps = [];

  const addStep = (x, y, z) => {
    steps.push({ block: material, x, y, z });
  };

  if (preset === "pillar") {
    for (let y = 0; y < height; y += 1) {
      addStep(originX, originY + y, originZ);
    }
    return steps;
  }

  if (preset === "wall") {
    for (let x = 0; x < width; x += 1) {
      for (let y = 0; y < height; y += 1) {
        addStep(originX + x, originY + y, originZ);
      }
    }
    return steps;
  }

  if (preset === "bridge") {
    for (let z = 0; z < length; z += 1) {
      for (let x = 0; x < width; x += 1) {
        addStep(originX + x, originY, originZ + z);
      }
    }
    return steps;
  }

  if (preset === "hut") {
    const roofY = originY + height - 1;
    for (let x = 0; x < width; x += 1) {
      for (let z = 0; z < length; z += 1) {
        addStep(originX + x, originY, originZ + z);
        addStep(originX + x, roofY, originZ + z);
      }
    }
    for (let y = 1; y < height - 1; y += 1) {
      for (let x = 0; x < width; x += 1) {
        addStep(originX + x, originY + y, originZ);
        addStep(originX + x, originY + y, originZ + length - 1);
      }
      for (let z = 1; z < length - 1; z += 1) {
        addStep(originX, originY + y, originZ + z);
        addStep(originX + width - 1, originY + y, originZ + z);
      }
    }
    return steps;
  }

  throw new Error(`Unsupported preset: ${preset}`);
}


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

  _pushChat(sender, message) {
    this.chatLog.push({ sender, message, timestamp: nowIso() });
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
    this._pushChat(this.config?.username || "DedalusBot", message);
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
}


class MineflayerSession {
  constructor() {
    this.bot = null;
    this.registry = null;
    this.pathfinder = null;
    this.chatLog = [];
    this.config = null;
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

  _pushChat(sender, message) {
    this.chatLog.push({ sender, message, timestamp: nowIso() });
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
        this._pushChat(username, message);
      }
    });

    bot.on("messagestr", (message) => {
      this._pushChat("server", message);
    });

    bot.once("error", (error) => {
      this._pushChat("error", error.message);
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
        this._pushChat("error", error.message);
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
      entities: Object.values(bot.entities)
        .filter((entity) => entity !== bot.entity)
        .slice(0, 8)
        .map((entity) => ({
          name: entity.name || entity.username || entity.type,
          kind: entity.type,
          x: Math.floor(entity.position.x),
          y: Math.floor(entity.position.y),
          z: Math.floor(entity.position.z),
        })),
      chat_backlog: this.chatLog.length,
    };
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
      nearby_entities: Object.values(bot.entities)
        .filter((entity) => entity !== bot.entity)
        .slice(0, 8)
        .map((entity) => ({
          name: entity.name || entity.username || entity.type,
          kind: entity.type,
          x: Math.floor(entity.position.x),
          y: Math.floor(entity.position.y),
          z: Math.floor(entity.position.z),
        })),
      objectives: [
        "Gather wood and stone for tool upgrades",
        "Smelt iron for armor and pickaxe",
        "Prepare blaze rods and ender pearls",
      ],
    };
  }

  async moveTo({ x, y, z, range = 1, timeout_ms = 30000 }) {
    const bot = this._requireBot();
    const { Movements, goals } = this.pathfinder;
    const movements = new Movements(bot);
    movements.canDig = true;
    const goal = new goals.GoalNear(x, y, z, range);
    bot.pathfinder.setMovements(movements);
    const operation = bot.pathfinder.goto(goal);
    const timeout = new Promise((_, reject) => {
      setTimeout(() => reject(new Error(`Timed out moving to ${x},${y},${z}`)), timeout_ms);
    });
    await Promise.race([operation, timeout]);
    return this.status();
  }

  async mineResource({ name, count = 1, max_distance = 32 }) {
    const bot = this._requireBot();
    const blockInfo = this.registry.blocksByName[name];
    if (!blockInfo) {
      throw new Error(`Unknown block name: ${name}`);
    }

    let mined = 0;
    while (mined < count) {
      const target = bot.findBlock({ matching: blockInfo.id, maxDistance: max_distance });
      if (!target) {
        break;
      }
      await this.moveTo({
        x: target.position.x,
        y: target.position.y,
        z: target.position.z,
        range: 2,
        timeout_ms: 30000,
      });
      await bot.dig(target, true);
      mined += 1;
    }

    return {
      action: "mine_resource",
      resource: name,
      mined,
      inventory: this._inventory(),
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
    const recipes = bot.recipesFor(itemInfo.id, null, count, table || null);
    if (!recipes || recipes.length === 0) {
      throw new Error(`No available recipe for ${item}.`);
    }
    await bot.craft(recipes[0], count, table || null);
    return {
      action: "craft_items",
      item,
      crafted: count,
      inventory: this._inventory(),
    };
  }

  async placeBlock({ block, x, y, z }) {
    const bot = this._requireBot();
    const inventoryItem = bot.inventory.items().find((itemInfo) => itemInfo.name === block);
    if (!inventoryItem) {
      throw new Error(`Item ${block} is not in inventory.`);
    }

    const target = new Vec3(x, y, z);
    const directions = [
      new Vec3(1, 0, 0),
      new Vec3(-1, 0, 0),
      new Vec3(0, 1, 0),
      new Vec3(0, -1, 0),
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
      throw new Error("Could not find a reference block for placement.");
    }

    await bot.equip(inventoryItem, "hand");
    await this.moveTo({ x, y, z, range: 3, timeout_ms: 30000 });
    await bot.placeBlock(reference, face);

    return {
      action: "place_block",
      block,
      position: { x, y, z },
      inventory: this._inventory(),
    };
  }

  async digBlock({ x, y, z }) {
    const bot = this._requireBot();
    const block = bot.blockAt(new Vec3(x, y, z));
    if (!block || block.name === "air") {
      throw new Error(`No diggable block at ${x},${y},${z}.`);
    }
    await this.moveTo({ x, y, z, range: 2, timeout_ms: 30000 });
    await bot.dig(block, true);
    return {
      action: "dig_block",
      block: block.name,
      position: { x, y, z },
      inventory: this._inventory(),
    };
  }

  async attackEntity({ name, count = 1 }) {
    const bot = this._requireBot();
    let defeated = 0;
    for (let attempt = 0; attempt < count; attempt += 1) {
      const entity = Object.values(bot.entities).find((candidate) => {
        const entityName = candidate.name || candidate.username || candidate.type;
        return entityName === name;
      });
      if (!entity) {
        break;
      }
      await this.moveTo({
        x: Math.floor(entity.position.x),
        y: Math.floor(entity.position.y),
        z: Math.floor(entity.position.z),
        range: 2,
        timeout_ms: 30000,
      });
      await bot.attack(entity);
      defeated += 1;
    }
    if (defeated === 0) {
      throw new Error(`No entity named ${name} found.`);
    }
    return {
      action: "attack_entity",
      target: name,
      defeated,
      inventory: this._inventory(),
    };
  }

  async sendChat({ message }) {
    const bot = this._requireBot();
    bot.chat(message);
    this._pushChat(bot.username, message);
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
    return { action: "equip_item", item, destination, inventory: this._inventory() };
  }

  async dropItem({ item, count = 1 }) {
    const bot = this._requireBot();
    const slot = bot.inventory.items().find((i) => i.name === item);
    if (!slot) {
      throw new Error(`Item ${item} not in inventory.`);
    }
    const toDrop = Math.min(count, slot.count);
    await bot.toss(slot.type, null, toDrop);
    return { action: "drop_item", item, count: toDrop, inventory: this._inventory() };
  }

  async eat({ item }) {
    const bot = this._requireBot();
    const slot = bot.inventory.items().find((i) => i.name === item);
    if (!slot) {
      throw new Error(`Item ${item} not in inventory.`);
    }
    await bot.equip(slot, "hand");
    await bot.consume();
    return { action: "eat", item, inventory: this._inventory() };
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
    const block = bot.blockAt(new Vec3(x, y, z));
    if (!block || !block.name?.includes("bed")) {
      throw new Error(`No bed at ${x},${y},${z}.`);
    }
    await this.moveTo({ x, y, z, range: 2, timeout_ms: 15000 });
    await bot.sleep(block);
    return { action: "sleep", position: { x, y, z } };
  }

  async wake() {
    const bot = this._requireBot();
    if (bot.isSleeping) {
      bot.wake();
    }
    return { action: "wake" };
  }

  async collectItems({ radius = 8 } = {}) {
    const bot = this._requireBot();
    const items = Object.values(bot.entities).filter((e) => e.name === "item" || e.objectType === "Item");
    let collected = 0;
    for (const entity of items) {
      const dist = bot.entity.position.distanceTo(entity.position);
      if (dist > radius) continue;
      try {
        await this.moveTo({
          x: Math.floor(entity.position.x),
          y: Math.floor(entity.position.y),
          z: Math.floor(entity.position.z),
          range: 2,
          timeout_ms: 10000,
        });
        collected += 1;
      } catch (_) {
        break;
      }
    }
    return { action: "collect_items", collected, radius, inventory: this._inventory() };
  }

  async fish() {
    const bot = this._requireBot();
    const rod = bot.inventory.items().find((i) => i.name === "fishing_rod");
    if (!rod) {
      throw new Error("No fishing_rod in inventory.");
    }
    await bot.equip(rod, "hand");
    await bot.fish();
    return { action: "fish", inventory: this._inventory() };
  }

  async mountEntity({ name }) {
    const bot = this._requireBot();
    const entity = Object.values(bot.entities).find((e) => (e.name || e.username || e.type) === name);
    if (!entity) {
      throw new Error(`No entity named ${name} found.`);
    }
    await this.moveTo({
      x: Math.floor(entity.position.x),
      y: Math.floor(entity.position.y),
      z: Math.floor(entity.position.z),
      range: 2,
      timeout_ms: 15000,
    });
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
    const entity = Object.values(bot.entities).find((e) => (e.name || e.username || e.type) === name);
    if (!entity) {
      throw new Error(`No entity named ${name} found.`);
    }
    await this.moveTo({
      x: Math.floor(entity.position.x),
      y: Math.floor(entity.position.y),
      z: Math.floor(entity.position.z),
      range: 3,
      timeout_ms: 15000,
    });
    await bot.activateEntity(entity);
    return { action: "interact_entity", target: name };
  }

  async stopMovement() {
    const bot = this._requireBot();
    if (bot.pathfinder) {
      bot.pathfinder.stop();
    }
    bot.clearControlStates();
    return { action: "stop_movement" };
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
        "/actions/send_chat": (payload) => session.sendChat(payload),
        "/actions/build_structure": (payload) => session.buildStructure(payload),
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
