/**
 * SpatialIndex — Grid-based spatial hash for fast hit testing and viewport culling.
 *
 * At 200+ nodes, we need O(1) lookups for "what's near this point?"
 * rather than iterating all nodes every frame.
 */

import type { Vec2 } from "./PhysicsEngine";

export interface SpatialEntry {
  id: string;
  x: number;
  y: number;
  radius: number;
}

export class SpatialIndex {
  private cellSize: number;
  private grid: Map<string, SpatialEntry[]>;
  private entries: Map<string, SpatialEntry>;

  constructor(cellSize: number = 80) {
    this.cellSize = cellSize;
    this.grid = new Map();
    this.entries = new Map();
  }

  private key(cx: number, cy: number): string {
    return `${cx},${cy}`;
  }

  private cellCoords(x: number, y: number): [number, number] {
    return [
      Math.floor(x / this.cellSize),
      Math.floor(y / this.cellSize),
    ];
  }

  /**
   * Clear and rebuild the index with new entries.
   */
  rebuild(entries: SpatialEntry[]) {
    this.grid.clear();
    this.entries.clear();

    for (const entry of entries) {
      this.entries.set(entry.id, entry);

      // Insert into all cells the entry's bounding box touches
      const r = entry.radius;
      const [minCx, minCy] = this.cellCoords(entry.x - r, entry.y - r);
      const [maxCx, maxCy] = this.cellCoords(entry.x + r, entry.y + r);

      for (let cx = minCx; cx <= maxCx; cx++) {
        for (let cy = minCy; cy <= maxCy; cy++) {
          const k = this.key(cx, cy);
          let cell = this.grid.get(k);
          if (!cell) {
            cell = [];
            this.grid.set(k, cell);
          }
          cell.push(entry);
        }
      }
    }
  }

  /**
   * Find the nearest entry to a point within maxDistance.
   * Returns null if nothing is within range.
   */
  nearest(point: Vec2, maxDistance: number): SpatialEntry | null {
    const [minCx, minCy] = this.cellCoords(point.x - maxDistance, point.y - maxDistance);
    const [maxCx, maxCy] = this.cellCoords(point.x + maxDistance, point.y + maxDistance);

    let closest: SpatialEntry | null = null;
    let closestDist = maxDistance;

    for (let cx = minCx; cx <= maxCx; cx++) {
      for (let cy = minCy; cy <= maxCy; cy++) {
        const cell = this.grid.get(this.key(cx, cy));
        if (!cell) continue;

        for (const entry of cell) {
          const dx = entry.x - point.x;
          const dy = entry.y - point.y;
          const dist = Math.sqrt(dx * dx + dy * dy) - entry.radius;

          if (dist < closestDist) {
            closestDist = dist;
            closest = entry;
          }
        }
      }
    }

    return closest;
  }

  /**
   * Find all entries within a rectangular viewport (in world space).
   */
  queryRect(left: number, top: number, right: number, bottom: number): SpatialEntry[] {
    const [minCx, minCy] = this.cellCoords(left, top);
    const [maxCx, maxCy] = this.cellCoords(right, bottom);

    const seen = new Set<string>();
    const results: SpatialEntry[] = [];

    for (let cx = minCx; cx <= maxCx; cx++) {
      for (let cy = minCy; cy <= maxCy; cy++) {
        const cell = this.grid.get(this.key(cx, cy));
        if (!cell) continue;

        for (const entry of cell) {
          if (seen.has(entry.id)) continue;
          seen.add(entry.id);

          // Check if entry overlaps viewport
          if (
            entry.x + entry.radius >= left &&
            entry.x - entry.radius <= right &&
            entry.y + entry.radius >= top &&
            entry.y - entry.radius <= bottom
          ) {
            results.push(entry);
          }
        }
      }
    }

    return results;
  }

  /**
   * Get entry by ID.
   */
  get(id: string): SpatialEntry | undefined {
    return this.entries.get(id);
  }
}
