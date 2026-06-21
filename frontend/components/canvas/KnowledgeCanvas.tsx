"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { GraphData, GraphNode, GraphEdge } from "@/lib/api";
import {
  createCamera, stepCamera, setCameraTarget,
  createMomentum, stepMomentum,
  createSimulation, stepSimulation, createDrift, getDriftOffset,
  lerp, clamp,
  type CameraState, type MomentumState, type Vec2,
  type ForceSimulation, type DriftParams,
} from "./PhysicsEngine";
import { SpatialIndex, type SpatialEntry } from "./SpatialIndex";

/* ── Visual constants ── */

const BG_COLOR = "#0c0e14";  // deep dark — almost black with a hint of blue

// Importance-based color palette (Obsidian-inspired)
function getNodeFill(node: GraphNode): string {
  if (node.is_hub || node.importance > 0.8) return "#4ade80";  // emerald hubs
  if (node.importance > 0.6) return "#86efac";                  // light green
  return "#94a3b8";                                              // slate gray
}

function getLabelColor(_node: GraphNode): string {
  return "rgba(210, 220, 235, 0.8)";
}

const EDGE_COLOR       = "rgba(148, 163, 184, 0.10)";
const EDGE_COLOR_FOCUS = "rgba(148, 163, 184, 0.35)";
const EDGE_WIDTH       = 0.5;
const EDGE_WIDTH_FOCUS = 1.2;

const MIN_ZOOM = 0.08;
const MAX_ZOOM = 4.0;
const NODE_BASE = 3;
const NODE_SCALE = 15;
const HOVER_RADIUS = 60;
const FOCUS_ZOOM = 1.4;
const SPREAD_FACTOR = 3.0;  // generous spacing

/* ── Types ── */

interface CanvasNode {
  id: string;
  x: number;
  y: number;
  radius: number;
  data: GraphNode;
  opacity: number;
  glowIntensity: number;
  drift: DriftParams;
  edgeCount: number;
}

interface CanvasEdge {
  source: string;
  target: string;
  data: GraphEdge;
}

export interface CanvasControls {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
}

interface Props {
  graphData: GraphData;
  onNodeFocus: (node: GraphNode | null, edges: GraphEdge[]) => void;
  focusedNodeId: string | null;
  controlsRef?: React.MutableRefObject<CanvasControls | null>;
}

/* ── Helpers ── */

function nodeRadius(importance: number): number {
  return NODE_BASE + importance * NODE_SCALE;
}

/** Respects the OS "reduce motion" setting — disables ambient drift when set. */
function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

function screenToWorld(sx: number, sy: number, cam: CameraState): Vec2 {
  const hw = typeof window !== 'undefined' ? window.innerWidth / 2 : 900;
  const hh = typeof window !== 'undefined' ? window.innerHeight / 2 : 500;
  return {
    x: (sx - hw) / cam.zoom.current + cam.x.current,
    y: (sy - hh) / cam.zoom.current + cam.y.current,
  };
}

/* ── Component ── */

export default function KnowledgeCanvas({ graphData, onNodeFocus, focusedNodeId, controlsRef }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef(0);
  const cameraRef = useRef<CameraState>(createCamera(900, 800, 0.35));
  const momentumRef = useRef<MomentumState>(createMomentum(0.93));
  const spatialRef = useRef(new SpatialIndex(100));
  const nodesRef = useRef<CanvasNode[]>([]);
  const edgesRef = useRef<CanvasEdge[]>([]);
  const nodeByIdRef = useRef<Map<string, CanvasNode>>(new Map());
  const adjacencyRef = useRef<Map<string, Set<string>>>(new Map());
  const simRef = useRef<ForceSimulation | null>(null);
  const hoveredRef = useRef<string | null>(null);
  const dragRef = useRef({ active: false, lastX: 0, lastY: 0 });
  const sizeRef = useRef({ w: 0, h: 0 });
  const entranceStartRef = useRef(0);
  const lastSpatialRebuildRef = useRef(0);
  const reducedMotion = useReducedMotion();
  const [ready, setReady] = useState(false);

  // ── Initialize graph data ──
  useEffect(() => {
    if (!graphData?.nodes?.length) return;

    // Count edges per node
    const edgeCounts = new Map<string, number>();
    for (const e of graphData.edges) {
      edgeCounts.set(e.data.source, (edgeCounts.get(e.data.source) || 0) + 1);
      edgeCounts.set(e.data.target, (edgeCounts.get(e.data.target) || 0) + 1);
    }

    // Build canvas nodes
    const nodes: CanvasNode[] = graphData.nodes.map((n) => {
      const ec = edgeCounts.get(n.data.id) || 0;
      return {
        id: n.data.id,
        x: n.position.x * SPREAD_FACTOR,
        y: n.position.y * SPREAD_FACTOR,
        radius: nodeRadius(n.data.importance),
        data: n.data,
        opacity: 0,
        glowIntensity: 0,
        drift: createDrift(n.data.importance, ec),
        edgeCount: ec,
      };
    });

    // Build canvas edges
    const edges: CanvasEdge[] = graphData.edges.map((e) => ({
      source: e.data.source,
      target: e.data.target,
      data: e.data,
    }));

    nodesRef.current = nodes;
    edgesRef.current = edges;

    // Precompute lookups so the render loop never does linear scans per node/edge.
    const byId = new Map<string, CanvasNode>();
    for (const n of nodes) byId.set(n.id, n);
    nodeByIdRef.current = byId;

    const adjacency = new Map<string, Set<string>>();
    for (const e of edges) {
      (adjacency.get(e.source) ?? adjacency.set(e.source, new Set()).get(e.source)!).add(e.target);
      (adjacency.get(e.target) ?? adjacency.set(e.target, new Set()).get(e.target)!).add(e.source);
    }
    adjacencyRef.current = adjacency;

    // ── Create force-directed simulation ──
    const simNodes = nodes.map((n) => ({
      id: n.id,
      x: n.x,
      y: n.y,
      importance: n.data.importance,
    }));
    const simEdges = edges.map((e) => ({
      source: e.source,
      target: e.target,
      strength: e.data.strength || 0.8,
    }));
    simRef.current = createSimulation(simNodes, simEdges, {
      repulsion: 12000,
      attraction: 0.002,
      damping: 0.94,          // fluid, watery damping
      centerGravity: 0.00008,
      maxVelocity: 3.0,
      idealEdgeLength: 250,
    });

    // Build spatial index
    const entries: SpatialEntry[] = nodes.map((n) => ({
      id: n.id, x: n.x, y: n.y, radius: n.radius + 15,
    }));
    spatialRef.current.rebuild(entries);

    // Center camera
    if (nodes.length > 0) {
      let cx = 0, cy = 0;
      for (const n of nodes) { cx += n.x; cy += n.y; }
      cx /= nodes.length; cy /= nodes.length;
      setCameraTarget(cameraRef.current, cx, cy, 0.35, true);
    }

    entranceStartRef.current = performance.now();
    setReady(true);
  }, [graphData]);

  // ── Focus camera ──
  useEffect(() => {
    if (!focusedNodeId) return;
    const node = nodeByIdRef.current.get(focusedNodeId);
    if (!node) return;
    setCameraTarget(cameraRef.current, node.x, node.y, FOCUS_ZOOM);
  }, [focusedNodeId]);

  // ── Canvas resize ──
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = window.innerWidth;
      const h = window.innerHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      sizeRef.current = { w, h };
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  // ── Render loop ──
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !ready) return;

    const render = () => {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const dpr = window.devicePixelRatio || 1;
      const w = sizeRef.current.w;
      const h = sizeRef.current.h;
      const cam = cameraRef.current;
      const mom = momentumRef.current;
      const sim = simRef.current;
      const now = performance.now();
      const entranceElapsed = (now - entranceStartRef.current) / 1000;

      // ── Step force-directed simulation (cools to rest, reheats on interaction) ──
      if (sim) {
        stepSimulation(sim);

        // Sync sim positions back to canvas nodes + optional ambient drift
        for (const node of nodesRef.current) {
          const simNode = sim.nodeMap.get(node.id);
          if (!simNode) continue;
          if (reducedMotion) {
            node.x = simNode.x;
            node.y = simNode.y;
          } else {
            const drift = getDriftOffset(node.drift, now);
            node.x = simNode.x + drift.x;
            node.y = simNode.y + drift.y;
          }
        }

        // Rebuild the spatial index on a real time throttle (~6×/sec), not every
        // frame. (The old `Math.floor(now/500) % 1` guard was always true.)
        if (now - lastSpatialRebuildRef.current > 160) {
          lastSpatialRebuildRef.current = now;
          const entries: SpatialEntry[] = nodesRef.current.map((n) => ({
            id: n.id, x: n.x, y: n.y, radius: n.radius + 15,
          }));
          spatialRef.current.rebuild(entries);
        }
      }

      // Step camera
      if (mom.active) {
        cam.x.target -= mom.vx / cam.zoom.current;
        cam.y.target -= mom.vy / cam.zoom.current;
        cam.x.current = cam.x.target;
        cam.y.current = cam.y.target;
        stepMomentum(mom);
      }
      stepCamera(cam);

      ctx.save();
      ctx.scale(dpr, dpr);

      // ── Clear ──
      ctx.fillStyle = BG_COLOR;
      ctx.fillRect(0, 0, w, h);

      const zoom = cam.zoom.current;
      const hw = w / 2;
      const hh = h / 2;

      const toScreen = (wx: number, wy: number): [number, number] => [
        (wx - cam.x.current) * zoom + hw,
        (wy - cam.y.current) * zoom + hh,
      ];

      // Viewport bounds
      const margin = 150 / zoom;
      const vpLeft = cam.x.current - hw / zoom - margin;
      const vpRight = cam.x.current + hw / zoom + margin;
      const vpTop = cam.y.current - hh / zoom - margin;
      const vpBottom = cam.y.current + hh / zoom + margin;

      const nodeById = nodeByIdRef.current;
      // Neighbors of the focused node — computed once per frame, not per node.
      const focusNeighbors = focusedNodeId ? adjacencyRef.current.get(focusedNodeId) : null;

      // ── Draw edges ──
      for (const edge of edgesRef.current) {
        const srcNode = nodeById.get(edge.source);
        const tgtNode = nodeById.get(edge.target);
        if (!srcNode || !tgtNode) continue;
        if (srcNode.opacity < 0.05 && tgtNode.opacity < 0.05) continue;

        const inView =
          (srcNode.x >= vpLeft && srcNode.x <= vpRight && srcNode.y >= vpTop && srcNode.y <= vpBottom) ||
          (tgtNode.x >= vpLeft && tgtNode.x <= vpRight && tgtNode.y >= vpTop && tgtNode.y <= vpBottom);
        if (!inView) continue;

        const [sx, sy] = toScreen(srcNode.x, srcNode.y);
        const [tx, ty] = toScreen(tgtNode.x, tgtNode.y);

        const isFocusedEdge = focusedNodeId && (edge.source === focusedNodeId || edge.target === focusedNodeId);

        let alpha = Math.min(srcNode.opacity, tgtNode.opacity);
        if (focusedNodeId) {
          alpha = isFocusedEdge ? alpha * 1.5 : alpha * 0.04;
        }
        if (edge.data.hierarchy_edge && zoom < 0.6) alpha *= 0.3;

        ctx.globalAlpha = clamp(alpha, 0, 1);
        ctx.strokeStyle = isFocusedEdge ? EDGE_COLOR_FOCUS : EDGE_COLOR;
        ctx.lineWidth = isFocusedEdge ? EDGE_WIDTH_FOCUS : EDGE_WIDTH;

        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(tx, ty);
        ctx.stroke();
      }

      ctx.globalAlpha = 1;

      // ── Draw nodes ──
      const nodes = nodesRef.current;
      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];

        // Entrance animation
        const staggerDelay = (i * 0.03);
        const entranceProg = clamp((entranceElapsed - staggerDelay) / 0.5, 0, 1);
        const eased = 1 - Math.pow(1 - entranceProg, 3);
        node.opacity = lerp(node.opacity, eased, 0.15);

        if (node.opacity < 0.01) continue;

        // Viewport cull
        if (node.x < vpLeft || node.x > vpRight || node.y < vpTop || node.y > vpBottom) continue;

        const [sx, sy] = toScreen(node.x, node.y);
        const screenR = node.radius * zoom;

        // Focus dimming (uses the precomputed adjacency set — no per-node scan)
        let focusMult = 1;
        if (focusedNodeId) {
          if (node.id === focusedNodeId) {
            focusMult = 1.0;
          } else {
            focusMult = focusNeighbors?.has(node.id) ? 0.8 : 0.1;
          }
        }

        // Hover glow
        const isHovered = hoveredRef.current === node.id;
        const targetGlow = isHovered ? 1 : (node.id === focusedNodeId ? 0.8 : 0);
        node.glowIntensity = lerp(node.glowIntensity, targetGlow, 0.12);

        const finalOpacity = node.opacity * focusMult;

        // Subtle glow ring on hover/focus
        if (node.glowIntensity > 0.05) {
          const glowR = screenR + 5 + node.glowIntensity * 10;
          const glowAlpha = node.glowIntensity * 0.3 * finalOpacity;
          ctx.beginPath();
          ctx.arc(sx, sy, glowR, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(74, 222, 128, ${glowAlpha.toFixed(3)})`;
          ctx.lineWidth = 1.5;
          ctx.globalAlpha = 1;
          ctx.stroke();
        }

        // Node body — clean solid circle
        ctx.globalAlpha = finalOpacity;
        ctx.fillStyle = getNodeFill(node.data);
        ctx.beginPath();
        ctx.arc(sx, sy, screenR, 0, Math.PI * 2);
        ctx.fill();

        // Focused ring
        if (node.id === focusedNodeId) {
          ctx.strokeStyle = "rgba(74, 222, 128, 0.7)";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(sx, sy, screenR + 4, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Labels — readable, clean
        const labelThreshold = node.data.is_hub ? 0.18 : (node.data.importance > 0.7 ? 0.25 : 0.4);
        if (zoom > labelThreshold && finalOpacity > 0.15 && screenR > 1.5) {
          const fontSize = clamp(12 * zoom, 10, 16);
          ctx.font = `500 ${fontSize}px Inter, system-ui, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";

          const labelOpacity = clamp((zoom - labelThreshold) / 0.25, 0, 0.85) * finalOpacity;
          ctx.fillStyle = `rgba(210, 220, 235, ${labelOpacity.toFixed(3)})`;
          ctx.fillText(node.data.label, sx, sy + screenR + 4);
        }

        ctx.globalAlpha = 1;
      }

      // ── Domain labels at low zoom ──
      if (zoom < 0.3) {
        const domainGroups = new Map<string, { cx: number; cy: number; count: number }>();
        for (const node of nodes) {
          if (node.opacity < 0.1) continue;
          const d = node.data.domain || "Unknown";
          const g = domainGroups.get(d) || { cx: 0, cy: 0, count: 0 };
          g.cx += node.x;
          g.cy += node.y;
          g.count++;
          domainGroups.set(d, g);
        }

        for (const [domain, g] of domainGroups) {
          if (g.count < 2) continue;
          const cx = g.cx / g.count;
          const cy = g.cy / g.count;
          const [sx, sy] = toScreen(cx, cy);
          const labelAlpha = clamp((0.3 - zoom) / 0.15, 0, 0.5);

          ctx.font = `300 ${clamp(16 / zoom * 0.3, 12, 20)}px Inter, system-ui, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = `rgba(148, 163, 184, ${labelAlpha.toFixed(3)})`;
          ctx.fillText(domain, sx, sy);
        }
      }

      ctx.restore();
      rafRef.current = requestAnimationFrame(render);
    };

    rafRef.current = requestAnimationFrame(render);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [ready, focusedNodeId, reducedMotion]);

  // ── Mouse handlers ──
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const cam = cameraRef.current;

    if (dragRef.current.active) {
      const dx = e.clientX - dragRef.current.lastX;
      const dy = e.clientY - dragRef.current.lastY;
      cam.x.current -= dx / cam.zoom.current;
      cam.y.current -= dy / cam.zoom.current;
      cam.x.target = cam.x.current;
      cam.y.target = cam.y.current;
      momentumRef.current.vx = dx;
      momentumRef.current.vy = dy;
      dragRef.current.lastX = e.clientX;
      dragRef.current.lastY = e.clientY;
      return;
    }

    const worldPos = screenToWorld(e.clientX, e.clientY, cam);
    const hit = spatialRef.current.nearest(worldPos, HOVER_RADIUS / cam.zoom.current);
    hoveredRef.current = hit?.id ?? null;

    const canvas = canvasRef.current;
    if (canvas) canvas.style.cursor = hit ? "pointer" : "grab";
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    momentumRef.current.active = false;
    momentumRef.current.vx = 0;
    momentumRef.current.vy = 0;

    const cam = cameraRef.current;
    const worldPos = screenToWorld(e.clientX, e.clientY, cam);
    const hit = spatialRef.current.nearest(worldPos, HOVER_RADIUS / cam.zoom.current);

    if (hit) {
      const node = nodeByIdRef.current.get(hit.id);
      if (node) {
        const connectedEdges = edgesRef.current
          .filter((edge) => edge.source === node.id || edge.target === node.id)
          .map((edge) => edge.data);
        onNodeFocus(node.data, connectedEdges);
      }
      return;
    }

    dragRef.current = { active: true, lastX: e.clientX, lastY: e.clientY };
    const canvas = canvasRef.current;
    if (canvas) canvas.style.cursor = "grabbing";
  }, [onNodeFocus]);

  const handleMouseUp = useCallback(() => {
    if (dragRef.current.active) {
      dragRef.current.active = false;
      const mom = momentumRef.current;
      if (Math.abs(mom.vx) > 1 || Math.abs(mom.vy) > 1) {
        mom.active = true;
      }
    }
    const canvas = canvasRef.current;
    if (canvas) canvas.style.cursor = hoveredRef.current ? "pointer" : "grab";
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const cam = cameraRef.current;
    const factor = e.deltaY > 0 ? 0.88 : 1.14;
    const newZoom = clamp(cam.zoom.target * factor, MIN_ZOOM, MAX_ZOOM);

    const worldBefore = screenToWorld(e.clientX, e.clientY, cam);
    cam.zoom.target = newZoom;

    const hw = sizeRef.current.w / 2;
    const hh = sizeRef.current.h / 2;
    cam.x.target = worldBefore.x - (e.clientX - hw) / newZoom;
    cam.y.target = worldBefore.y - (e.clientY - hh) / newZoom;
  }, []);

  const handleCanvasClick = useCallback((e: React.MouseEvent) => {
    const cam = cameraRef.current;
    const worldPos = screenToWorld(e.clientX, e.clientY, cam);
    const hit = spatialRef.current.nearest(worldPos, HOVER_RADIUS / cam.zoom.current);
    if (!hit) {
      onNodeFocus(null, []);
    }
  }, [onNodeFocus]);

  const zoomIn = useCallback(() => {
    const cam = cameraRef.current;
    cam.zoom.target = clamp(cam.zoom.target * 1.4, MIN_ZOOM, MAX_ZOOM);
  }, []);

  const zoomOut = useCallback(() => {
    const cam = cameraRef.current;
    cam.zoom.target = clamp(cam.zoom.target * 0.7, MIN_ZOOM, MAX_ZOOM);
  }, []);

  const fitView = useCallback(() => {
    const nodes = nodesRef.current;
    if (!nodes.length) return;
    let cx = 0, cy = 0;
    for (const n of nodes) { cx += n.x; cy += n.y; }
    cx /= nodes.length; cy /= nodes.length;
    setCameraTarget(cameraRef.current, cx, cy, 0.35);
    onNodeFocus(null, []);
  }, [onNodeFocus]);

  useEffect(() => {
    if (!controlsRef) return;
    controlsRef.current = { zoomIn, zoomOut, fitView };
    return () => { controlsRef.current = null; };
  }, [controlsRef, zoomIn, zoomOut, fitView]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0"
      style={{
        cursor: "grab",
        opacity: ready ? 1 : 0,
        transition: "opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1)",
      }}
      onMouseMove={handleMouseMove}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      onClick={handleCanvasClick}
    />
  );
}
