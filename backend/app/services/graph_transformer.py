from collections import deque
import math
import random
from ..config import get_logger

logger = get_logger(__name__)

# Spatial layout dimensions
CANVAS_WIDTH = 1800
CANVAS_HEIGHT = 1600
CENTER_X = CANVAS_WIDTH / 2
CENTER_Y = CANVAS_HEIGHT / 2

# Galaxy layout constants
HUB_CORE_RADIUS = 120          # Central hub cluster radius
DOMAIN_INNER_RADIUS = 260      # Inner edge of domain sectors
DOMAIN_MID_RADIUS = 480        # Middle of domain sectors
DOMAIN_OUTER_RADIUS = 720      # Outer edge of domain sectors
DOMAIN_SECTOR_ANGLE = math.radians(65)  # Angular spread per domain within its sector
MIN_NODE_DISTANCE = 55         # Collision avoidance threshold
SEMANTIC_PULL_WEIGHT = 0.15    # How much cross-domain edges pull nodes

Y_LAYERS = {"root": DOMAIN_INNER_RADIUS, "branch": DOMAIN_MID_RADIUS, "leaf": DOMAIN_OUTER_RADIUS}


def _build_tree(concepts: list[dict]) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    """Build adjacency: parent→children, child→parent, root ids."""
    children_of: dict[str, list[str]] = {}
    parent_of: dict[str, str] = {}
    roots: list[str] = []

    id_set = {c["id"] for c in concepts}
    id_to_c = {c["id"]: c for c in concepts}

    for c in concepts:
        cid = c["id"]
        pid = c.get("parent_id")
        if pid and pid in id_set:
            parent_of[cid] = pid
            children_of.setdefault(pid, []).append(cid)
        else:
            roots.append(cid)

    # Also populate from children_ids for robustness
    for c in concepts:
        for child_id in c.get("children_ids", []):
            if child_id in id_set:
                children_of.setdefault(c["id"], []).append(child_id)
                if child_id not in parent_of:
                    parent_of[child_id] = c["id"]

    return children_of, parent_of, roots


def _compute_depth(cid: str, parent_of: dict[str, str], id_to_c: dict[str, dict], max_depth: int = 50) -> int:
    """Compute tree depth (root = 0, each level +1)."""
    depth = 0
    current = cid
    for _ in range(max_depth):
        pid = parent_of.get(current)
        if not pid or pid not in id_to_c:
            break
        depth += 1
        current = pid
    return depth


def compute_positions(
    concepts: list[dict],
    relationships: list[dict] | None = None,
    hub_concepts: list[dict] | None = None,
) -> dict[str, dict[str, float]]:
    """Compute semantic galaxy layout positions.

    Spatial metaphor:
    - High hub-score foundational concepts anchor the galactic core.
    - Each domain forms an orbital sector (galaxy arm) radiating outward.
    - Abstraction level controls radial depth (root→inner, branch→mid, leaf→outer).
    - Cross-domain relationships create subtle semantic bridges between sectors.
    - Collision detection prevents node overlap within sectors.

    Returns {concept_id: {x, y}} for preset Cytoscape layout.
    """
    if not concepts:
        return {}

    id_to_c = {c["id"]: c for c in concepts}
    n = len(concepts)

    # ── Identify hub concepts and domains ──
    hub_ids: set[str] = set()
    hub_scores: dict[str, float] = {}
    if hub_concepts:
        for h in hub_concepts:
            hub_ids.add(h.get("concept_id", ""))
            hub_scores[h.get("concept_id", "")] = h.get("hub_score", 0.5)

    # Sort hubs by score descending
    sorted_hubs = sorted(hub_ids, key=lambda cid: hub_scores.get(cid, 0), reverse=True)

    # Group concepts by domain
    domain_ids: dict[str, list[str]] = {}
    domain_order: list[str] = []
    for c in concepts:
        d = c.get("domain", "Unclassified")
        if d not in domain_ids:
            domain_ids[d] = []
            domain_order.append(d)
        domain_ids[d].append(c["id"])

    # Sort domains by size
    domain_order.sort(key=lambda d: len(domain_ids[d]), reverse=True)

    # ── Build cross-domain edge adjacency ──
    edge_adj: dict[str, list[str]] = {}
    if relationships:
        for rel in relationships:
            if rel.get("cross_domain"):
                sid = rel.get("source_id", "")
                tid = rel.get("target_id", "")
                if sid in id_to_c and tid in id_to_c:
                    edge_adj.setdefault(sid, []).append(tid)
                    edge_adj.setdefault(tid, []).append(sid)

    # ── Assign positions ──
    positions: dict[str, dict[str, float]] = {}
    domain_pos: list[str] = []  # Track domain assignment order for sectors

    # Seed deterministic random for consistent jitter
    rng = random.Random(42)

    # 1. Place hub concepts in the galactic core
    hub_count = len(sorted_hubs)
    for i, cid in enumerate(sorted_hubs):
        if hub_count <= 1:
            angle = 0
        else:
            angle = (2 * math.pi * i) / hub_count
        radius = HUB_CORE_RADIUS * (0.3 + 0.7 * (i / max(hub_count, 1)))
        x = CENTER_X + math.cos(angle) * radius
        y = CENTER_Y + math.sin(angle) * radius
        positions[cid] = {"x": x, "y": y}

    # 2. Place remaining concepts in domain sectors
    for di, domain in enumerate(domain_order):
        cids = [cid for cid in domain_ids[domain] if cid not in hub_ids]
        if not cids:
            continue

        # Sector angle assignment
        sector_center_angle = (2 * math.pi * di) / max(len(domain_order), 1)
        domain_pos.append(domain)

        # Sort within domain: roots first (inner), then branches, then leaves (outer)
        cids.sort(key=lambda cid: (
            {"root": 0, "branch": 1, "leaf": 2}.get(id_to_c[cid].get("abstraction_level", "branch"), 1),
            -id_to_c[cid].get("importance", 0.5),
        ))

        m = len(cids)
        for j, cid in enumerate(cids):
            level = id_to_c[cid].get("abstraction_level", "branch")
            base_radius = Y_LAYERS.get(level, DOMAIN_MID_RADIUS)

            # Distribute concepts along the radial axis within their level band
            band_start = base_radius - 40
            band_end = base_radius + 120
            radial_pos = band_start + (band_end - band_start) * (j / max(m, 1))

            # Angular spread within sector
            half_angle = DOMAIN_SECTOR_ANGLE / 2
            angle_offset = half_angle * (1.0 - (j / max(m, 1)))
            # Alternate sides for visual spread
            sign = 1 if j % 2 == 0 else -1
            angle = sector_center_angle + sign * max(angle_offset, half_angle * 0.15)

            x = CENTER_X + math.cos(angle) * radial_pos
            y = CENTER_Y + math.sin(angle) * radial_pos

            # Subtle jitter for organic feel
            x += rng.uniform(-8, 8)
            y += rng.uniform(-8, 8)

            positions[cid] = {"x": x, "y": y}

    # 3. Apply semantic pull from cross-domain edges (gentle)
    if edge_adj:
        for _ in range(2):
            pulls: dict[str, list[tuple[float, float]]] = {}
            for cid, neighbors in edge_adj.items():
                if cid not in positions:
                    continue
                cx, cy = positions[cid]["x"], positions[cid]["y"]
                for nid in neighbors:
                    if nid not in positions:
                        continue
                    nx, ny = positions[nid]["x"], positions[nid]["y"]
                    dx, dy = nx - cx, ny - cy
                    dist = math.hypot(dx, dy) or 1
                    # Pull toward neighbor (moderate pull)
                    pull = SEMANTIC_PULL_WEIGHT * (dist * 0.3)
                    pulls.setdefault(cid, []).append((
                        cx + (dx / dist) * pull,
                        cy + (dy / dist) * pull,
                    ))

            for cid, candidates in pulls.items():
                if candidates:
                    avg_x = sum(p[0] for p in candidates) / len(candidates)
                    avg_y = sum(p[1] for p in candidates) / len(candidates)
                    positions[cid] = {"x": avg_x, "y": avg_y}

    # 4. Collision avoidance — iterative push-apart with decay
    for iteration in range(8):
        moved = False
        ids = list(positions.keys())
        rng.shuffle(ids)
        # Decay force over iterations for stability
        force_scale = 0.6 * (1.0 - iteration / 12)
        for i, a in enumerate(ids):
            for j, b in enumerate(ids):
                if i >= j:
                    continue
                pa = positions[a]
                pb = positions[b]
                dx = pb["x"] - pa["x"]
                dy = pb["y"] - pa["y"]
                dist = math.hypot(dx, dy)
                if 0 < dist < MIN_NODE_DISTANCE:
                    moved = True
                    overlap = MIN_NODE_DISTANCE - dist
                    ux = dx / dist if dist > 0 else 1
                    uy = dy / dist if dist > 0 else 0
                    push = overlap * force_scale
                    pa["x"] -= ux * push
                    pa["y"] -= uy * push
                    pb["x"] += ux * push
                    pb["y"] += uy * push
                elif dist == 0:
                    # Perfectly overlapping — nudge randomly
                    moved = True
                    pa["x"] += rng.uniform(-MIN_NODE_DISTANCE * 0.3, MIN_NODE_DISTANCE * 0.3)
                    pa["y"] += rng.uniform(-MIN_NODE_DISTANCE * 0.3, MIN_NODE_DISTANCE * 0.3)
        if not moved:
            break

    # 5. Clamp to canvas bounds with padding
    margin = 80
    for cid, pos in positions.items():
        pos["x"] = max(margin, min(CANVAS_WIDTH - margin, pos["x"]))
        pos["y"] = max(margin, min(CANVAS_HEIGHT - margin, pos["y"]))

    hub_placed = sum(1 for cid in hub_ids if cid in positions)
    logger.info(
        "Galaxy layout: %d concepts across %d domains — %d hub(s) in core, %d cross-domain pull edges",
        len(positions), len(domain_order), hub_placed,
        sum(len(v) for v in edge_adj.values()) // 2 if edge_adj else 0,
    )

    return positions


def transform_graph(
    concepts: list[dict],
    relationships: list[dict],
    hub_concepts: list[dict],
) -> dict:
    """Transform pipeline output into Cytoscape-ready elements with galaxy layout positions."""
    positions = compute_positions(concepts, relationships, hub_concepts)
    id_to_c = {c["id"]: c for c in concepts}
    hub_ids = {h["concept_id"] for h in hub_concepts}
    hub_scores = {h["concept_id"]: h["hub_score"] for h in hub_concepts}

    nodes: list[dict] = []
    edges: list[dict] = []

    for c in concepts:
        cid = c["id"]
        pos = positions.get(cid, {"x": 0, "y": 0})
        is_hub = cid in hub_ids
        nodes.append({
            "data": {
                "id": cid,
                "label": c.get("label", ""),
                "summary": c.get("summary", ""),
                "concept_type": c.get("concept_type", "abstraction"),
                "abstraction_level": c.get("abstraction_level", "branch"),
                "educational_role": c.get("educational_role", "supporting"),
                "importance": c.get("importance", 0.5),
                "domain": c.get("domain", "Unclassified"),
                "theme": c.get("theme", ""),
                "hub_score": hub_scores.get(cid, 0),
                "is_hub": is_hub,
                "parent_id": c.get("parent_id"),
                "children_ids": c.get("children_ids", []),
            },
            "position": pos,
        })

    edge_ids: set[tuple[str, str]] = set()

    # Hierarchy edges (parent → child)
    for c in concepts:
        pid = c.get("parent_id")
        if pid and pid in id_to_c:
            key = (pid, c["id"])
            if key not in edge_ids:
                edge_ids.add(key)
                edges.append({
                    "data": {
                        "id": f"hier_{pid}_{c['id']}",
                        "source": pid,
                        "target": c["id"],
                        "relationship_type": "hierarchy",
                        "strength": 0.95,
                        "hierarchy_edge": True,
                        "cross_domain": False,
                        "reasoning": "",
                    },
                })

    # Semantic edges (relationships from Stage 3)
    for rel in (relationships or []):
        sid = rel.get("source_id", "")
        tid = rel.get("target_id", "")
        if sid not in id_to_c or tid not in id_to_c:
            continue
        key = (sid, tid)
        reverse_key = (tid, sid)
        if key in edge_ids or reverse_key in edge_ids:
            continue
        edge_ids.add(key)
        edges.append({
            "data": {
                "id": rel.get("id", f"sem_{sid}_{tid}"),
                "source": sid,
                "target": tid,
                "relationship_type": rel.get("relationship_type", "semantically_linked"),
                "strength": rel.get("strength", 0.5),
                "hierarchy_edge": False,
                "cross_domain": rel.get("cross_domain", False),
                "reasoning": rel.get("reasoning", ""),
            },
        })

    logger.info(
        "Transformed graph: %d nodes, %d edges (%d hierarchy, %d semantic)",
        len(nodes), len(edges),
        sum(1 for e in edges if e["data"].get("hierarchy_edge")),
        sum(1 for e in edges if not e["data"].get("hierarchy_edge")),
    )

    return {
        "nodes": nodes,
        "edges": edges,
        "hub_concept_ids": list(hub_ids),
    }
