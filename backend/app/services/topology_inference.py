import json
import re
import time
import uuid
import asyncio
from .deepseek_client import async_chat
from ..config import (
    TOPOLOGY_INFERENCE_MAX_TOKENS,
    MAX_CANDIDATE_PAIRS,
    MAX_RELATIONSHIPS,
    MAX_EDGES_PER_CONCEPT,
    get_logger,
)

logger = get_logger(__name__)

RELATIONSHIP_CONFIDENCE_THRESHOLD = 0.65
TOPOLOGY_BATCH_SIZE = 8  # Pairs per LLM call — small enough to avoid truncation

RELATIONSHIP_SYSTEM = """\
You are an expert educational topology analyst. Your task is to identify meaningful, mechanistic educational relationships between concepts extracted from an educational document.

Your output will be used to build a knowledge graph that helps learners understand how ideas connect. Shallow or generic connections are WORSE than no connection — they create noise that obscures real understanding.

─── RELATIONSHIP TYPES ───

prerequisite_of   — A must be understood BEFORE B. Without understanding A, B is incomprehensible.
                    Example: "Linear Algebra" → prerequisite_of → "Principal Component Analysis"
depends_on        — B's meaning, existence, or value depends on A. Weaker than prerequisite.
                    Example: "Yield Strength" depends_on "Dislocation Density"
causes            — A directly produces, triggers, or leads to B through a known mechanism.
                    Example: "Rapid Cooling" causes "Martensitic Transformation"
influences        — A modifies, shapes, or affects B without strict causation.
                    Example: "Grain Size" influences "Mechanical Properties"
enables           — A makes B possible, practical, or achievable.
                    Example: "Fourier Transform" enables "Frequency Domain Analysis"
specializes       — B is a more specific instance, case, or subtype of A.
                    Example: "Quenching" specializes "Heat Treatment"
contrasts_with    — A and B are alternatives, opposites, or in pedagogical tension.
                    Example: "Ductile Fracture" contrasts_with "Brittle Fracture"
derived_from      — B is logically, mathematically, or conceptually derived from A.
                    Example: "Stress-Strain Curve" derived_from "Hooke's Law"
part_of           — B is a component, phase, or sub-process of A.
                    Example: "Nucleation" part_of "Solidification"
applies_to        — A is applied in, used for, or relevant to understanding B.
                    Example: "Fick's Law" applies_to "Carburizing"
transforms_into   — A changes, converts, or evolves into B under specific conditions.
                    Example: "Austenite" transforms_into "Martensite"
semantically_linked — LAST RESORT. Only if a genuine educational connection exists but no other type fits.

─── QUALITY RULES ───

1. MECHANISTIC REASONING REQUIRED: For every relationship, you must articulate a specific "because" — the mechanism or logic that connects A to B. If you cannot explain WHY beyond "they appear in the same document" or "both are types of X", skip the pair.

2. DIRECTIONALITY IS MANDATORY: "A and B are related" is USELESS. Every relationship must have a clear source → target direction. Ask: "Which concept feeds into the other?"

3. BE CONSERVATIVE: It is MUCH better to return 3 strong relationships than 8 weak ones. The graph benefits from precision, not volume.

4. STRENGTH CALIBRATION:
   - 0.90-1.0 = Textbook-level, universally accepted connection (e.g., "Temperature" causes "Thermal Expansion")
   - 0.75-0.89 = Well-supported by the document's content, clear educational connection
   - 0.65-0.74 = Plausible but requires inference beyond what the text explicitly states
   - Below 0.65 = Do NOT include

─── ANTI-PATTERNS (EXPLICITLY REJECTED) ───

× "Both are important concepts in manufacturing" — surface similarity, not a relationship
× "Understanding A helps understand B" — applies to almost everything, useless
× "They share the same domain" — domain co-occurrence is not a relationship
× "They are often discussed together" — co-occurrence is not causation
× Any relationship where the reasoning is just a restatement of the type name

─── GOOD EXAMPLE ───
{
  "source_label": "Cooling Rate",
  "target_label": "Grain Size",
  "relationship_type": "causes",
  "strength": 0.92,
  "reasoning": "Faster cooling rates suppress grain growth by limiting atomic diffusion time, producing finer grain structures. This is a fundamental metallurgical principle described by nucleation kinetics."
}

─── BAD EXAMPLE (DO NOT PRODUCE) ───
{
  "source_label": "Heat Treatment",
  "target_label": "Hardness",
  "relationship_type": "influences",
  "strength": 0.8,
  "reasoning": "Heat treatment affects hardness because both are related to material properties."
}

Output as a JSON object with a "relationships" array, nothing else:
{
  "relationships": [
    {
      "source_label": "Concept A",
      "target_label": "Concept B",
      "relationship_type": "prerequisite_of",
      "strength": 0.85,
      "reasoning": "One-sentence mechanistic explanation with a specific 'because'."
    }
  ]
}"""



def _build_concept_summary(concepts: list[dict]) -> str:
    """Build a compact summary of all concepts for the LLM prompt."""
    lines: list[str] = []
    for c in concepts:
        kids = c.get("children_ids", [])
        parent = " (root)" if not c.get("parent_id") else f" (child of {c.get('parent_id', '?')[:8]})"
        children_note = f" [{len(kids)} children]" if kids else ""
        lines.append(
            f"- [{c.get('concept_type', '?')}] {c['label']}: {c.get('summary', '')[:120]}{parent}{children_note}"
        )
    return "\n".join(lines)


def _get_parent_chain(concept: dict, id_to_concept: dict[str, dict], max_depth: int = 20) -> set[str]:
    """Get all ancestor IDs of a concept."""
    ancestors: set[str] = set()
    current = concept.get("parent_id")
    for _ in range(max_depth):
        if not current:
            break
        ancestors.add(current)
        parent = id_to_concept.get(current)
        if not parent:
            break
        current = parent.get("parent_id")
    return ancestors


def _same_hierarchy_branch(a: dict, b: dict, id_to_concept: dict[str, dict]) -> bool:
    """Check if two concepts share a common ancestor within 3 levels."""
    a_ancestors = _get_parent_chain(a, id_to_concept)
    b_ancestors = _get_parent_chain(b, id_to_concept)
    return bool(a_ancestors & b_ancestors)


def _is_parent_child(a: dict, b: dict) -> bool:
    """Check if a is parent of b or vice versa."""
    aid = a["id"]
    bid = b["id"]
    return (
        a.get("parent_id") == bid
        or b.get("parent_id") == aid
        or bid in a.get("children_ids", [])
        or aid in b.get("children_ids", [])
    )


def generate_candidate_pairs(concepts: list[dict]) -> list[tuple[dict, dict]]:
    """Generate promising concept pairs for relationship inference.

    Strategy:
    - Prefer pairs in different hierarchy branches (different parent chains)
    - Prefer cross-domain pairs
    - Include pairs where one is high-importance foundation and the other is mechanism/application
    - Exclude parent-child pairs (already covered by hierarchy)
    - Cap at MAX_CANDIDATE_PAIRS
    """
    if len(concepts) < 2:
        return []

    id_to_concept = {c["id"]: c for c in concepts}

    scored_pairs: list[tuple[float, dict, dict]] = []

    for i, a in enumerate(concepts):
        for j, b in enumerate(concepts):
            if i >= j:
                continue

            if _is_parent_child(a, b):
                continue

            score = 0.0

            # Cross-domain bonus
            if a.get("domain") and b.get("domain") and a["domain"] != b["domain"]:
                score += 2.0
            else:
                score += 0.5

            # Different hierarchy branch bonus
            if not _same_hierarchy_branch(a, b, id_to_concept):
                score += 1.5

            # High importance foundation paired with mechanism/process/application
            a_imp = a.get("importance", 0.5)
            b_imp = b.get("importance", 0.5)
            imp_score = (a_imp + b_imp) / 2
            score += imp_score

            a_type = a.get("concept_type", "")
            b_type = b.get("concept_type", "")
            type_pair = {a_type, b_type}
            if "foundation" in type_pair and ("mechanism" in type_pair or "application" in type_pair or "process" in type_pair):
                score += 1.0

            # Bonus for pairs that share a theme
            if a.get("theme") and b.get("theme") and a["theme"] == b["theme"]:
                score += 0.5

            scored_pairs.append((score, a, b))

    scored_pairs.sort(key=lambda x: x[0], reverse=True)
    selected = [(a, b) for _, a, b in scored_pairs[:MAX_CANDIDATE_PAIRS]]

    same_branch = sum(1 for a, b in selected if _same_hierarchy_branch(a, b, id_to_concept))
    diff_branch = len(selected) - same_branch
    cross_domain = sum(1 for a, b in selected if a.get("domain") != b.get("domain"))

    logger.info(
        "Generated %d candidate pairs (%d diff-branch, %d cross-domain)",
        len(selected), diff_branch, cross_domain,
    )

    return selected


def _parse_relationships(raw: str) -> list[dict]:
    """Parse LLM response into relationship dicts. Tolerates malformed JSON,
    code fences, truncated arrays, and extraneous text."""
    original = raw.strip()

    # Strip markdown fences
    raw = original
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # Try direct JSON parse
    try:
        data = json.loads(raw)
        return _extract_relationships(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting a JSON object { ... }
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return _extract_relationships(data)
        except (json.JSONDecodeError, ValueError):
            pass

    # Try extracting a JSON array [ ... ]
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return _extract_relationships(data)
        except (json.JSONDecodeError, ValueError):
            pass

    # Last resort: try line-by-line extraction of relationship-like objects
    # Match patterns like: {"source_label": "...", "target_label": "...", ...}
    loose = re.findall(
        r'\{\s*"source_label"\s*:\s*"([^"]+)"\s*,\s*"target_label"\s*:\s*"([^"]+)"[^}]*\}',
        raw,
    )
    if loose:
        logger.warning(
            "Partial parse: recovered %d loose relationship(s) from malformed response",
            len(loose),
        )
        return [
            {
                "source_label": src.strip(),
                "target_label": tgt.strip(),
                "relationship_type": "semantically_linked",
                "strength": max(RELATIONSHIP_CONFIDENCE_THRESHOLD, 0.7),
                "reasoning": "Recovered from partially malformed LLM output",
            }
            for src, tgt in loose
        ]

    logger.warning(
        "Could not parse relationship JSON — raw(%d): %s",
        len(original), original[:300],
    )
    return []


def _extract_relationships(data: object) -> list[dict]:
    """Extract relationship list from parsed JSON."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "relationships" in data:
        rels = data["relationships"]
        if isinstance(rels, list):
            return rels
    raise ValueError(f"Unexpected JSON shape: {type(data).__name__}")


def _validate_relationship(rel: dict) -> dict | None:
    allowed_types = {
        "prerequisite_of", "depends_on", "causes", "influences", "enables",
        "specializes", "contrasts_with", "derived_from", "part_of",
        "applies_to", "transforms_into", "semantically_linked",
    }

    rel_type = str(rel.get("relationship_type", "")).strip().lower()
    if rel_type not in allowed_types:
        rel_type = "semantically_linked"

    try:
        strength = float(rel.get("strength", 0.5))
        strength = max(0.0, min(1.0, strength))
    except (ValueError, TypeError):
        strength = 0.5

    if strength < RELATIONSHIP_CONFIDENCE_THRESHOLD:
        return None

    source_label = str(rel.get("source_label", "")).strip()
    target_label = str(rel.get("target_label", "")).strip()
    if not source_label or not target_label or source_label == target_label:
        return None

    return {
        "source_label": source_label,
        "target_label": target_label,
        "relationship_type": rel_type,
        "strength": strength,
        "reasoning": str(rel.get("reasoning", "")).strip(),
    }


def _normalize_label(label: str) -> str:
    label = label.lower().strip()
    label = re.sub(r"[^\w\s]", "", label)
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _build_batch_concept_summary(pair_concepts: set[str], concepts: list[dict]) -> str:
    """Build a compact summary of only the concepts relevant to a batch."""
    lines: list[str] = []
    for c in concepts:
        if c["label"] in pair_concepts:
            kids = c.get("children_ids", [])
            parent = " (root)" if not c.get("parent_id") else ""
            children_note = f" [{len(kids)} children]" if kids else ""
            lines.append(
                f"- [{c.get('concept_type', '?')}] {c['label']}: {c.get('summary', '')[:80]}{parent}{children_note}"
            )
    return "\n".join(lines)


async def _process_batch(
    batch: list[tuple[dict, dict]],
    batch_idx: int,
    total_batches: int,
    concepts: list[dict],
    semaphore: asyncio.Semaphore,
    update_progress=None
) -> list[dict]:
    async with semaphore:
        batch_start = time.monotonic()
        batch_relationships = []

        pair_labels: set[str] = set()
        for a, b in batch:
            pair_labels.add(a["label"])
            pair_labels.add(b["label"])

        concept_summary = _build_batch_concept_summary(pair_labels, concepts)

        pair_lines: list[str] = []
        for a, b in batch:
            pair_lines.append(
                f"Pair {len(pair_lines) + 1}: '{a['label']}' [{a.get('concept_type', '?')}] "
                f"<-> '{b['label']}' [{b.get('concept_type', '?')}]"
            )
        pairs_text = "\n".join(pair_lines)

        prompt_est = len(RELATIONSHIP_SYSTEM) + len(concept_summary) + len(pairs_text)
        logger.info(
            "Batch %d/%d: %d pair(s), ~%d prompt chars",
            batch_idx + 1, total_batches, len(batch), prompt_est,
        )

        try:
            raw = await async_chat(
                messages=[
                    {"role": "system", "content": RELATIONSHIP_SYSTEM},
                    {"role": "user", "content": (
                        "Concepts referenced in this batch:\n"
                        f"{concept_summary}\n\n"
                        "Pairs to evaluate. Determine if a meaningful educational relationship "
                        "exists for each pair. Skip pairs where no real connection exists.\n\n"
                        f"{pairs_text}"
                    )},
                ],
                temperature=0.15,
                max_tokens=TOPOLOGY_INFERENCE_MAX_TOKENS,
            )
        except Exception as e:
            logger.error("Failed to process batch %d/%d: %s", batch_idx + 1, total_batches, e)
            if update_progress:
                update_progress()
            return []

        batch_elapsed = time.monotonic() - batch_start
        logger.info(
            "Batch %d/%d response: %d chars in %.1fs",
            batch_idx + 1, total_batches, len(raw), batch_elapsed,
        )

        try:
            parsed = _parse_relationships(raw)
        except Exception as exc:
            logger.warning(
                "Batch %d/%d parse failed: %s — raw(%d): %s",
                batch_idx + 1, total_batches, exc, len(raw),
                raw[:200],
            )
            if update_progress:
                update_progress()
            return []

        batch_valid = 0
        batch_malformed = 0
        for rel in parsed:
            try:
                valid = _validate_relationship(rel)
                if valid:
                    batch_relationships.append(valid)
                    batch_valid += 1
                else:
                    batch_malformed += 1
            except Exception:
                batch_malformed += 1

        logger.info(
            "Batch %d/%d: %d valid, %d malformed/dropped",
            batch_idx + 1, total_batches, batch_valid, batch_malformed,
        )
        
        if update_progress:
            update_progress()

        return batch_relationships


async def async_infer_relationships(
    concepts: list[dict],
    candidate_pairs: list[tuple[dict, dict]],
    status_callback=None
) -> list[dict]:
    """Batch-judge candidate pairs via DeepSeek to identify semantic relationships concurrently."""
    if not candidate_pairs:
        return []

    batch_size = max(1, min(TOPOLOGY_BATCH_SIZE, len(candidate_pairs)))

    batches: list[list[tuple[dict, dict]]] = []
    for i in range(0, len(candidate_pairs), batch_size):
        batches.append(candidate_pairs[i : i + batch_size])

    logger.info(
        "Inferring %d candidate pairs in %d batch(es) of ≤%d each",
        len(candidate_pairs), len(batches), batch_size,
    )

    completed_batches = 0
    total_batches = len(batches)

    def update_progress():
        nonlocal completed_batches
        completed_batches += 1
        if status_callback:
            status_callback(f"Building topology ({completed_batches}/{total_batches})")

    semaphore = asyncio.Semaphore(10)

    tasks = [
        _process_batch(batch, i, total_batches, concepts, semaphore, update_progress)
        for i, batch in enumerate(batches)
    ]

    results = await asyncio.gather(*tasks)

    all_relationships: list[dict] = []
    for batch_rels in results:
        all_relationships.extend(batch_rels)

    logger.info(
        "Topology inference complete: %d total relationships from %d batches",
        len(all_relationships), len(batches),
    )
    return all_relationships


def _resolve_relationship_ids(
    relationships: list[dict],
    label_to_id: dict[str, str],
) -> list[dict]:
    """Translate source_label/target_label to concept IDs. Drop unresolvable edges."""
    resolved: list[dict] = []
    for rel in relationships:
        src_norm = _normalize_label(rel["source_label"])
        tgt_norm = _normalize_label(rel["target_label"])
        src_id = label_to_id.get(src_norm)
        tgt_id = label_to_id.get(tgt_norm)
        if not src_id or not tgt_id or src_id == tgt_id:
            continue
        resolved.append({
            "id": uuid.uuid4().hex[:10],
            "source_id": src_id,
            "target_id": tgt_id,
            "source_label": rel["source_label"],
            "target_label": rel["target_label"],
            "relationship_type": rel["relationship_type"],
            "strength": rel["strength"],
            "reasoning": rel["reasoning"],
        })
    return resolved


def _deduplicate_edges(relationships: list[dict]) -> list[dict]:
    """Remove duplicate edges (same source-target pair), keeping highest strength.
    Also handle reverse-duplicates for symmetric relationship types."""
    symmetric_types = {"contrasts_with", "semantically_linked"}

    seen: dict[tuple[str, str], dict] = {}

    for rel in relationships:
        key = (rel["source_id"], rel["target_id"])
        reverse_key = (rel["target_id"], rel["source_id"])

        rtype = rel["relationship_type"]

        # For symmetric types, also check reverse
        if rtype in symmetric_types:
            existing = seen.get(reverse_key)
            if existing and existing["strength"] < rel["strength"]:
                del seen[reverse_key]
                seen[key] = rel
            elif existing:
                continue  # existing is stronger or equal
            else:
                if key in seen:
                    if rel["strength"] > seen[key]["strength"]:
                        seen[key] = rel
                else:
                    seen[key] = rel
        else:
            if key in seen:
                if rel["strength"] > seen[key]["strength"]:
                    seen[key] = rel
            elif reverse_key not in seen:
                seen[key] = rel
            # If reverse exists and it's directional, keep the one with higher strength
            elif reverse_key in seen:
                existing = seen[reverse_key]
                if rel["strength"] > existing["strength"]:
                    del seen[reverse_key]
                    seen[key] = rel

    return list(seen.values())


def _ensure_no_prereq_cycles(relationships: list[dict]) -> list[dict]:
    """Remove prerequisite/dependency edges that would create cycles."""
    directional = {"prerequisite_of", "depends_on", "derived_from", "enables", "causes"}

    # Build adjacency for directional edges
    adj: dict[str, list[str]] = {}
    for rel in relationships:
        if rel["relationship_type"] in directional:
            adj.setdefault(rel["source_id"], []).append(rel["target_id"])

    def creates_cycle(src: str, tgt: str, max_depth: int = 20) -> bool:
        visited: set[str] = {src}
        stack = [tgt]
        for _ in range(max_depth):
            if not stack:
                return False
            current = stack.pop()
            if current == src:
                return True
            if current in visited:
                continue
            visited.add(current)
            for neighbor in adj.get(current, []):
                stack.append(neighbor)

    safe: list[dict] = []
    removed = 0
    for rel in relationships:
        if rel["relationship_type"] in directional:
            if creates_cycle(rel["source_id"], rel["target_id"]):
                logger.warning(
                    "Cycle prevented: %s -> %s (%s)",
                    rel.get("source_label", "?"),
                    rel.get("target_label", "?"),
                    rel["relationship_type"],
                )
                removed += 1
                continue
        safe.append(rel)

    if removed:
        logger.info("Removed %d cycle-forming relationship(s)", removed)

    return safe


def _cull_edges_per_concept(relationships: list[dict]) -> list[dict]:
    """Limit maximum edges per concept to prevent hub overconnection."""
    edge_counts: dict[str, int] = {}
    for rel in relationships:
        edge_counts[rel["source_id"]] = edge_counts.get(rel["source_id"], 0) + 1
        edge_counts[rel["target_id"]] = edge_counts.get(rel["target_id"], 0) + 1

    # Sort relationships by strength descending
    sorted_rels = sorted(relationships, key=lambda r: r["strength"], reverse=True)

    kept: list[dict] = []
    counts: dict[str, int] = {}
    for rel in sorted_rels:
        src_count = counts.get(rel["source_id"], 0)
        tgt_count = counts.get(rel["target_id"], 0)
        if src_count < MAX_EDGES_PER_CONCEPT and tgt_count < MAX_EDGES_PER_CONCEPT:
            kept.append(rel)
            counts[rel["source_id"]] = src_count + 1
            counts[rel["target_id"]] = tgt_count + 1

    dropped = len(relationships) - len(kept)
    if dropped:
        logger.info("Culled %d edges to respect max %d per concept", dropped, MAX_EDGES_PER_CONCEPT)

    return kept


def _mark_cross_domain(relationships: list[dict], id_to_concept: dict[str, dict]) -> list[dict]:
    """Mark whether each edge connects concepts in different domains."""
    for rel in relationships:
        src = id_to_concept.get(rel["source_id"])
        tgt = id_to_concept.get(rel["target_id"])
        rel["cross_domain"] = (
            bool(src and tgt and src.get("domain") != tgt.get("domain"))
        )
    return relationships


def detect_hub_concepts(concepts: list[dict], relationships: list[dict]) -> list[dict]:
    """Identify foundational hub concepts using graph-theoretic measures.

    Hub concepts are those with:
    - High connectivity (many edges)
    - Cross-domain reach (edges to concepts in other domains)
    - High importance
    """
    if not relationships:
        return []

    id_to_concept = {c["id"]: c for c in concepts}

    # Compute degree and cross-domain connections
    degree: dict[str, int] = {}
    cross_domain_degree: dict[str, int] = {}
    for rel in relationships:
        degree[rel["source_id"]] = degree.get(rel["source_id"], 0) + 1
        degree[rel["target_id"]] = degree.get(rel["target_id"], 0) + 1
        if rel.get("cross_domain"):
            cross_domain_degree[rel["source_id"]] = cross_domain_degree.get(rel["source_id"], 0) + 1
            cross_domain_degree[rel["target_id"]] = cross_domain_degree.get(rel["target_id"], 0) + 1

    if not degree:
        return []

    max_degree = max(degree.values()) if degree else 1
    max_cross = max(cross_domain_degree.values()) if cross_domain_degree else 1

    # Score each concept as a hub
    hub_scores: list[tuple[float, str]] = []
    for cid, c in id_to_concept.items():
        d = degree.get(cid, 0)
        cd = cross_domain_degree.get(cid, 0)
        imp = c.get("importance", 0.5)

        if d == 0:
            continue

        # Normalize and combine
        degree_norm = d / max_degree
        cross_norm = cd / max_cross if max_cross > 0 else 0
        hub_score = (degree_norm * 0.4) + (cross_norm * 0.35) + (imp * 0.25)

        hub_scores.append((hub_score, cid))

    hub_scores.sort(key=lambda x: x[0], reverse=True)

    # Only keep concepts with meaningful hub score
    threshold = 0.3
    hubs = []
    for score, cid in hub_scores:
        if score < threshold:
            break
        c = id_to_concept.get(cid)
        if not c:
            continue
        hubs.append({
            "concept_id": cid,
            "label": c.get("label", ""),
            "hub_score": round(score, 3),
            "degree": degree.get(cid, 0),
            "cross_domain_edges": cross_domain_degree.get(cid, 0),
        })

    # Cap at most 5 hub concepts
    hubs = hubs[:5]

    if hubs:
        logger.info(
            "Detected %d hub concept(s): %s",
            len(hubs),
            ", ".join(h["label"] for h in hubs),
        )

    return hubs


async def async_assemble_topology(concepts: list[dict], global_understanding: dict | None = None, status_callback=None) -> tuple[list[dict], list[dict]]:
    """Main Stage 3 orchestration: infer relationships and detect hub concepts."""
    if len(concepts) < 2:
        logger.info("Skipping topology inference: fewer than 2 concepts")
        return [], []

    logger.info("=== Stage 3: Knowledge Topology Inference ===")

    id_to_concept = {c["id"]: c for c in concepts}

    # 1. Generate candidate pairs
    candidate_pairs = generate_candidate_pairs(concepts)

    # 2. Infer relationships via LLM
    raw_relationships = await async_infer_relationships(concepts, candidate_pairs, status_callback=status_callback)

    # 3. Resolve concept IDs from labels
    label_to_id = {}
    for c in concepts:
        norm = _normalize_label(c["label"])
        if norm:
            label_to_id[norm] = c["id"]

    relationships = _resolve_relationship_ids(raw_relationships, label_to_id)

    # 4. Deduplicate edges
    relationships = _deduplicate_edges(relationships)

    # 5. Ensure no prerequisite cycles
    relationships = _ensure_no_prereq_cycles(relationships)

    # 6. Mark cross-domain edges
    relationships = _mark_cross_domain(relationships, id_to_concept)

    # 7. Cull per-concept edge maximum
    relationships = _cull_edges_per_concept(relationships)

    # 8. Cap total relationships
    relationships = relationships[:MAX_RELATIONSHIPS]

    # 9. Detect hub concepts
    hub_concepts = detect_hub_concepts(concepts, relationships)

    cross_domain_count = sum(1 for r in relationships if r.get("cross_domain"))
    logger.info(
        "Final topology: %d relationships (%d cross-domain), %d hub concepts",
        len(relationships), cross_domain_count, len(hub_concepts),
    )

    return relationships, hub_concepts
