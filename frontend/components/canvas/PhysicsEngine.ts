/**
 * PhysicsEngine — Force-directed simulation + spring-damper camera.
 *
 * Provides continuous, fluid, organic motion to the graph:
 * - Nodes repel each other (Coulomb's law)
 * - Edges attract connected nodes (Hooke's law / spring)
 * - Velocity damping creates fluid, watery deceleration
 * - Ambient drift adds gentle sine-wave wobble on top
 */

export interface SpringValue {
  current: number;
  target: number;
  velocity: number;
}

export interface Vec2 {
  x: number;
  y: number;
}

export interface CameraState {
  x: SpringValue;
  y: SpringValue;
  zoom: SpringValue;
}

export interface SpringConfig {
  stiffness: number;
  damping: number;
  restThreshold: number;
}

// Default spring — responsive but not snappy
export const CAMERA_SPRING: SpringConfig = {
  stiffness: 0.06,
  damping: 0.82,
  restThreshold: 0.01,
};

// Softer spring for ambient/idle motion
export const GENTLE_SPRING: SpringConfig = {
  stiffness: 0.03,
  damping: 0.9,
  restThreshold: 0.005,
};

// Quick spring for hover response
export const QUICK_SPRING: SpringConfig = {
  stiffness: 0.12,
  damping: 0.78,
  restThreshold: 0.02,
};

export function createSpring(initial: number): SpringValue {
  return { current: initial, target: initial, velocity: 0 };
}

export function createCamera(x: number, y: number, zoom: number): CameraState {
  return {
    x: createSpring(x),
    y: createSpring(y),
    zoom: createSpring(zoom),
  };
}

export function stepSpring(spring: SpringValue, config: SpringConfig): boolean {
  const force = (spring.target - spring.current) * config.stiffness;
  spring.velocity = (spring.velocity + force) * config.damping;
  spring.current += spring.velocity;

  const settled =
    Math.abs(spring.target - spring.current) < config.restThreshold &&
    Math.abs(spring.velocity) < config.restThreshold;

  if (settled) {
    spring.current = spring.target;
    spring.velocity = 0;
  }

  return settled;
}

export function stepCamera(camera: CameraState, config: SpringConfig = CAMERA_SPRING): boolean {
  const sx = stepSpring(camera.x, config);
  const sy = stepSpring(camera.y, config);
  const sz = stepSpring(camera.zoom, config);
  return sx && sy && sz;
}

export function setCameraTarget(
  camera: CameraState,
  x: number,
  y: number,
  zoom: number,
  snap: boolean = false,
) {
  camera.x.target = x;
  camera.y.target = y;
  camera.zoom.target = zoom;

  if (snap) {
    camera.x.current = x;
    camera.y.current = y;
    camera.zoom.current = zoom;
    camera.x.velocity = 0;
    camera.y.velocity = 0;
    camera.zoom.velocity = 0;
  }
}

/* ── Momentum ── */

export interface MomentumState {
  vx: number;
  vy: number;
  active: boolean;
  friction: number;
}

export function createMomentum(friction: number = 0.92): MomentumState {
  return { vx: 0, vy: 0, active: false, friction };
}

export function stepMomentum(state: MomentumState): boolean {
  if (!state.active) return true;
  state.vx *= state.friction;
  state.vy *= state.friction;
  if (Math.abs(state.vx) < 0.05 && Math.abs(state.vy) < 0.05) {
    state.vx = 0;
    state.vy = 0;
    state.active = false;
    return true;
  }
  return false;
}

/* ── Force-Directed Simulation ── */

export interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  mass: number;        // heavier nodes resist movement more
  pinned: boolean;     // pinned nodes don't move (e.g. dragged)
}

export interface SimEdge {
  source: string;
  target: string;
  strength: number;    // spring constant for this edge
}

export interface ForceSimulation {
  nodes: SimNode[];
  edges: SimEdge[];
  nodeMap: Map<string, SimNode>;
  config: ForceConfig;
  alpha: number;           // simulation "heat"; forces scale with it and it decays to 0
}

export interface ForceConfig {
  repulsion: number;       // Coulomb constant (node-node repulsion)
  attraction: number;      // Hooke constant (edge spring pull)
  damping: number;         // velocity decay per frame (0.95 = fluid, 0.99 = icy)
  centerGravity: number;   // gentle pull toward center to prevent drift-away
  maxVelocity: number;     // cap velocity to prevent explosions
  idealEdgeLength: number; // rest length for edge springs
  alphaDecay: number;      // per-frame multiplicative cooldown of alpha
  alphaMin: number;        // below this, the simulation is considered settled and frozen
}

const DEFAULT_FORCE_CONFIG: ForceConfig = {
  repulsion: 8000,
  attraction: 0.003,
  damping: 0.92,
  centerGravity: 0.0001,
  maxVelocity: 4.0,
  idealEdgeLength: 200,
  alphaDecay: 0.985,
  alphaMin: 0.02,
};

export function createSimulation(
  nodes: { id: string; x: number; y: number; importance: number }[],
  edges: { source: string; target: string; strength: number }[],
  config: Partial<ForceConfig> = {},
): ForceSimulation {
  const cfg = { ...DEFAULT_FORCE_CONFIG, ...config };

  const simNodes: SimNode[] = nodes.map((n) => ({
    id: n.id,
    x: n.x,
    y: n.y,
    vx: 0,
    vy: 0,
    mass: 1 + n.importance * 3, // important nodes are heavier
    pinned: false,
  }));

  const simEdges: SimEdge[] = edges.map((e) => ({
    source: e.source,
    target: e.target,
    strength: e.strength,
  }));

  const nodeMap = new Map<string, SimNode>();
  for (const n of simNodes) nodeMap.set(n.id, n);

  return { nodes: simNodes, edges: simEdges, nodeMap, config: cfg, alpha: 1 };
}

/**
 * Advance the simulation by one tick.
 * This applies repulsion, attraction, center gravity, damping, and velocity capping.
 * Call this every frame for fluid motion.
 */
export function stepSimulation(sim: ForceSimulation): void {
  const { nodes, edges, nodeMap, config } = sim;
  const n = nodes.length;
  if (n === 0) return;

  // Once cooled, the layout is at rest — skip the O(n²) force pass entirely.
  // This is the difference between a graph that idles at ~0% CPU and one that
  // spins the fan forever.
  if (sim.alpha < config.alphaMin) {
    sim.alpha = 0;
    return;
  }

  const alpha = sim.alpha;

  // Compute centroid for center gravity
  let cx = 0, cy = 0;
  for (const node of nodes) { cx += node.x; cy += node.y; }
  cx /= n; cy /= n;

  // ── Repulsion (brute-force all-pairs, O(n²)) ──
  // For graphs under ~500 nodes this is fast enough at 60fps, and the alpha
  // cooldown above means it only runs while the layout is actually moving.
  for (let i = 0; i < n; i++) {
    const a = nodes[i];
    if (a.pinned) continue;

    for (let j = i + 1; j < n; j++) {
      const b = nodes[j];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let distSq = dx * dx + dy * dy;
      if (distSq < 1) distSq = 1; // avoid division by zero
      const dist = Math.sqrt(distSq);

      // Coulomb repulsion: F = k / d²  (scaled by simulation heat)
      const force = (config.repulsion / distSq) * alpha;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;

      a.vx -= fx / a.mass;
      a.vy -= fy / a.mass;
      if (!b.pinned) {
        b.vx += fx / b.mass;
        b.vy += fy / b.mass;
      }
    }
  }

  // ── Attraction (edges as springs) ──
  for (const edge of edges) {
    const a = nodeMap.get(edge.source);
    const b = nodeMap.get(edge.target);
    if (!a || !b) continue;

    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;

    // Hooke's law: F = k * (d - rest)  (scaled by simulation heat)
    const displacement = dist - config.idealEdgeLength;
    const force = displacement * config.attraction * edge.strength * alpha;
    const fx = (dx / dist) * force;
    const fy = (dy / dist) * force;

    if (!a.pinned) { a.vx += fx / a.mass; a.vy += fy / a.mass; }
    if (!b.pinned) { b.vx -= fx / b.mass; b.vy -= fy / b.mass; }
  }

  // ── Center gravity (gentle pull to prevent graph from drifting away) ──
  for (const node of nodes) {
    if (node.pinned) continue;
    node.vx -= (node.x - cx) * config.centerGravity * alpha;
    node.vy -= (node.y - cy) * config.centerGravity * alpha;
  }

  // ── Apply velocity: damping + position update ──
  for (const node of nodes) {
    if (node.pinned) continue;

    node.vx *= config.damping;
    node.vy *= config.damping;

    // Clamp velocity
    const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy);
    if (speed > config.maxVelocity) {
      node.vx = (node.vx / speed) * config.maxVelocity;
      node.vy = (node.vy / speed) * config.maxVelocity;
    }

    node.x += node.vx;
    node.y += node.vy;
  }

  // Cool the simulation toward rest.
  sim.alpha *= config.alphaDecay;
}

/* ── Ambient Drift (layered on top of simulation) ── */

export interface DriftParams {
  phaseX: number;
  phaseY: number;
  speedX: number;
  speedY: number;
  amplitude: number;
}

export function createDrift(importance: number, edgeCount: number): DriftParams {
  const connectivityFactor = clamp(1.0 - (importance * 0.5 + Math.min(edgeCount, 8) * 0.06), 0.15, 1.0);
  return {
    phaseX: Math.random() * Math.PI * 2,
    phaseY: Math.random() * Math.PI * 2,
    speedX: 0.0002 + Math.random() * 0.0003,
    speedY: 0.00015 + Math.random() * 0.00025,
    amplitude: (3 + Math.random() * 8) * connectivityFactor,
  };
}

export function getDriftOffset(drift: DriftParams, timeMs: number): Vec2 {
  return {
    x: Math.sin(timeMs * drift.speedX + drift.phaseX) * drift.amplitude,
    y: Math.cos(timeMs * drift.speedY + drift.phaseY) * drift.amplitude,
  };
}

/* ── Utilities ── */

export function lerp(current: number, target: number, rate: number): number {
  return current + (target - current) * rate;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function distance(a: Vec2, b: Vec2): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}
