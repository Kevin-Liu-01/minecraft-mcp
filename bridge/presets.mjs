/**
 * Building preset generators.
 * Each function returns an array of {x, y, z, block} placements
 * sorted bottom-up (ascending Y) so blocks always have a reference.
 */

function _sort(blocks) {
  return blocks.sort((a, b) => a.y - b.y || a.x - b.x || a.z - b.z);
}

// ── Basic shapes ─────────────────────────────────────────────

export function pillar(ox, oy, oz, { height = 5, material = "dirt" }) {
  const h = Math.max(4, height);
  const blocks = [];
  for (let y = 0; y < h; y++) blocks.push({ x: ox, y: oy + y, z: oz, block: material });
  return blocks;
}

export function wall(ox, oy, oz, { width = 5, height = 4, material = "cobblestone" }) {
  const blocks = [];
  for (let x = 0; x < width; x++)
    for (let y = 0; y < height; y++)
      blocks.push({ x: ox + x, y: oy + y, z: oz, block: material });
  return _sort(blocks);
}

export function floor(ox, oy, oz, { width = 5, length = 5, material = "oak_planks" }) {
  const blocks = [];
  for (let x = 0; x < width; x++)
    for (let z = 0; z < length; z++)
      blocks.push({ x: ox + x, y: oy, z: oz + z, block: material });
  return blocks;
}

// ── Structures ───────────────────────────────────────────────

export function house(ox, oy, oz, { width = 5, length = 5, height = 4, material = "oak_planks" }) {
  const blocks = [];
  const roofY = oy + height - 1;

  for (let x = 0; x < width; x++)
    for (let z = 0; z < length; z++) {
      blocks.push({ x: ox + x, y: oy, z: oz + z, block: material });
      blocks.push({ x: ox + x, y: roofY, z: oz + z, block: material });
    }

  for (let y = 1; y < height - 1; y++) {
    for (let x = 0; x < width; x++) {
      blocks.push({ x: ox + x, y: oy + y, z: oz, block: material });
      blocks.push({ x: ox + x, y: oy + y, z: oz + length - 1, block: material });
    }
    for (let z = 1; z < length - 1; z++) {
      blocks.push({ x: ox, y: oy + y, z: oz + z, block: material });
      blocks.push({ x: ox + width - 1, y: oy + y, z: oz + z, block: material });
    }
  }

  const doorX = ox + Math.floor(width / 2);
  const doorZ = oz;
  return _sort(blocks.filter(
    (b) => !(b.x === doorX && b.z === doorZ && (b.y === oy + 1 || b.y === oy + 2))
  ));
}

export function hut(ox, oy, oz, { material = "oak_planks" }) {
  const blocks = [];
  const W = 3, L = 3, H = 3;
  const doorX = ox + Math.floor(W / 2);
  const doorZ = oz;

  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++)
      for (let z = 0; z < L; z++) {
        // skip interior (only the single center block at y=1)
        if (x > 0 && x < W - 1 && z > 0 && z < L - 1 && y > 0 && y < H - 1) continue;
        // door opening: front-center at y=0 and y=1
        if (x === doorX - ox && z === 0 && y >= 0 && y <= 1) continue;
        blocks.push({ x: ox + x, y: oy + y, z: oz + z, block: material });
      }
  return _sort(blocks);
}

export function shelter(ox, oy, oz, { material = "cobblestone" }) {
  return house(ox, oy, oz, { width: 3, length: 3, height: 3, material });
}

export function bridge(ox, oy, oz, { width = 3, length = 8, material = "oak_planks" }) {
  const blocks = [];
  for (let z = 0; z < length; z++) {
    for (let x = 0; x < width; x++)
      blocks.push({ x: ox + x, y: oy, z: oz + z, block: material });
    blocks.push({ x: ox - 1, y: oy + 1, z: oz + z, block: material });
    blocks.push({ x: ox + width, y: oy + 1, z: oz + z, block: material });
  }
  return _sort(blocks);
}

export function stairs(ox, oy, oz, { height = 5, width = 3, material = "cobblestone" }) {
  const blocks = [];
  for (let step = 0; step < height; step++)
    for (let x = 0; x < width; x++)
      blocks.push({ x: ox + x, y: oy + step, z: oz + step, block: material });
  return _sort(blocks);
}

export function fence(ox, oy, oz, { width = 7, length = 7, material = "oak_fence" }) {
  const blocks = [];
  for (let x = 0; x < width; x++) {
    blocks.push({ x: ox + x, y: oy, z: oz, block: material });
    blocks.push({ x: ox + x, y: oy, z: oz + length - 1, block: material });
  }
  for (let z = 1; z < length - 1; z++) {
    blocks.push({ x: ox, y: oy, z: oz + z, block: material });
    blocks.push({ x: ox + width - 1, y: oy, z: oz + z, block: material });
  }
  return blocks;
}

export function pool(ox, oy, oz, { width = 5, length = 5, depth = 3, material = "stone_bricks" }) {
  const blocks = [];
  for (let d = 0; d < depth; d++) {
    const y = oy - d;
    for (let x = 0; x < width; x++) {
      blocks.push({ x: ox + x, y, z: oz, block: material });
      blocks.push({ x: ox + x, y, z: oz + length - 1, block: material });
    }
    for (let z = 1; z < length - 1; z++) {
      blocks.push({ x: ox, y, z: oz + z, block: material });
      blocks.push({ x: ox + width - 1, y, z: oz + z, block: material });
    }
  }
  for (let x = 0; x < width; x++)
    for (let z = 0; z < length; z++)
      blocks.push({ x: ox + x, y: oy - depth, z: oz + z, block: material });
  return _sort(blocks);
}

export function farm(ox, oy, oz, { width = 5, length = 5, material = "farmland" }) {
  const blocks = [];
  for (let x = 0; x < width; x++)
    for (let z = 0; z < length; z++)
      blocks.push({ x: ox + x, y: oy, z: oz + z, block: material });
  for (let x = 0; x < width; x++) {
    blocks.push({ x: ox + x, y: oy + 1, z: oz - 1, block: "oak_fence" });
    blocks.push({ x: ox + x, y: oy + 1, z: oz + length, block: "oak_fence" });
  }
  for (let z = 0; z < length; z++) {
    blocks.push({ x: ox - 1, y: oy + 1, z: oz + z, block: "oak_fence" });
    blocks.push({ x: ox + width, y: oy + 1, z: oz + z, block: "oak_fence" });
  }
  return _sort(blocks);
}

// ── New presets ──────────────────────────────────────────────

export function pyramid(ox, oy, oz, { height = 5, material = "sandstone" }) {
  const blocks = [];
  for (let y = 0; y < height; y++) {
    const size = height - y;
    const startX = ox - size + 1;
    const startZ = oz - size + 1;
    for (let x = 0; x < size * 2 - 1; x++)
      for (let z = 0; z < size * 2 - 1; z++)
        blocks.push({ x: startX + x, y: oy + y, z: startZ + z, block: material });
  }
  return _sort(blocks);
}

export function arch(ox, oy, oz, { width = 5, height = 5, material = "stone_bricks" }) {
  const blocks = [];
  for (let y = 0; y < height; y++) {
    blocks.push({ x: ox, y: oy + y, z: oz, block: material });
    blocks.push({ x: ox + width - 1, y: oy + y, z: oz, block: material });
  }
  for (let x = 1; x < width - 1; x++)
    blocks.push({ x: ox + x, y: oy + height - 1, z: oz, block: material });
  return _sort(blocks);
}

export function watchtower(ox, oy, oz, { height = 8, material = "cobblestone" }) {
  const blocks = [];
  for (let y = 0; y < height; y++)
    blocks.push({ x: ox, y: oy + y, z: oz, block: material });
  const topY = oy + height;
  for (let x = -1; x <= 1; x++)
    for (let z = -1; z <= 1; z++)
      blocks.push({ x: ox + x, y: topY, z: oz + z, block: material });
  for (let x = -1; x <= 1; x++) {
    blocks.push({ x: ox + x, y: topY + 1, z: oz - 1, block: material });
    blocks.push({ x: ox + x, y: topY + 1, z: oz + 1, block: material });
  }
  blocks.push({ x: ox - 1, y: topY + 1, z: oz, block: material });
  blocks.push({ x: ox + 1, y: topY + 1, z: oz, block: material });
  return _sort(blocks);
}

export function ring(ox, oy, oz, { radius = 4, height = 1, material = "stone" }) {
  const blocks = [];
  for (let y = 0; y < height; y++)
    for (let x = -radius; x <= radius; x++)
      for (let z = -radius; z <= radius; z++) {
        const distSq = x * x + z * z;
        if (distSq <= radius * radius && distSq >= (radius - 1) * (radius - 1))
          blocks.push({ x: ox + x, y: oy + y, z: oz + z, block: material });
      }
  return _sort(blocks);
}

// ── Lookup table ────────────────────────────────────────────

const PRESETS = {
  pillar, tower: pillar,
  wall,
  floor, platform: floor,
  house, cabin: house, cottage: house,
  hut,
  shelter,
  bridge,
  stairs, staircase: stairs,
  fence, enclosure: fence,
  pool,
  farm,
  pyramid,
  arch,
  watchtower,
  ring, circle: ring,
};

export function getPreset(name) {
  return PRESETS[name.toLowerCase()] || null;
}

export function listPresets() {
  return Object.keys(PRESETS);
}
