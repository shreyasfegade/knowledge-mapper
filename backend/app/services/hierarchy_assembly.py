import uuid
import re
from ..config import MAX_TOTAL_CONCEPTS, get_logger

logger = get_logger(__name__)


def _normalize(label: str) -> str:
    label = label.lower().strip()
    label = re.sub(r"[^\w\s]", "", label)
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _deduplicate(concepts: list[dict]) -> list[dict]:
    """Hierarchy-aware deduplication — keeps the concept with richer metadata."""
    if len(concepts) <= 1:
        return concepts

    seen: dict[str, int] = {}
    unique: list[dict] = []

    for c in concepts:
        norm = _normalize(c["label"])
        if not norm:
            continue
        if norm in seen:
            idx = seen[norm]
            existing = unique[idx]
            # Keep the one with higher confidence, or if equal, richer metadata
            if c["confidence"] > existing["confidence"]:
                unique[idx] = c
            elif c["confidence"] == existing["confidence"]:
                # Prefer non-default types/levels/roles
                new_richness = (
                    (1 if c.get("concept_type") != "process" else 0)
                    + (1 if c.get("abstraction_level") != "branch" else 0)
                    + (1 if c.get("educational_role") != "supporting" else 0)
                )
                old_richness = (
                    (1 if existing.get("concept_type") != "process" else 0)
                    + (1 if existing.get("abstraction_level") != "branch" else 0)
                    + (1 if existing.get("educational_role") != "supporting" else 0)
                )
                if new_richness > old_richness:
                    unique[idx] = c
        else:
            seen[norm] = len(unique)
            unique.append(c)

    return unique


def _assign_ids(concepts: list[dict]) -> list[dict]:
    """Assign stable UUIDs to each concept."""
    for c in concepts:
        c["id"] = uuid.uuid4().hex[:10]
    return concepts


def _build_label_to_id(concepts: list[dict]) -> dict[str, str]:
    """Map normalized labels to concept IDs."""
    mapping: dict[str, str] = {}
    for c in concepts:
        mapping[_normalize(c["label"])] = c["id"]
    return mapping


def _resolve_parents(concepts: list[dict], label_to_id: dict[str, str]) -> list[dict]:
    """Translate parent_labels to parent_ids. Resolve conflicts (at most one parent)."""
    for c in concepts:
        parent_labels = c.get("parent_labels", [])
        if not isinstance(parent_labels, list):
            c["parent_id"] = None
            c["parent_labels"] = []
            continue

        matched_ids = []
        matched_labels = []
        for pl in parent_labels:
            norm = _normalize(pl)
            if norm and norm in label_to_id:
                pid = label_to_id[norm]
                if pid != c["id"]:
                    matched_ids.append(pid)
                    matched_labels.append(pl)

        if len(matched_ids) > 1:
            # Keep only the first match — we don't support multi-parent yet
            logger.debug(
                "Concept '%s' had %d parents, keeping first",
                c["label"], len(matched_ids),
            )
            c["parent_id"] = matched_ids[0]
            c["parent_labels"] = [matched_labels[0]]
        elif len(matched_ids) == 1:
            c["parent_id"] = matched_ids[0]
            c["parent_labels"] = [matched_labels[0]]
        else:
            c["parent_id"] = None
            c["parent_labels"] = []

    return concepts


def _ensure_acyclic(concepts: list[dict]) -> list[dict]:
    """Detach concepts that create cycles in the parent chain."""
    id_to_concept = {c["id"]: c for c in concepts}

    def detect_cycle(start_id: str, max_depth: int = 20) -> bool:
        visited: set[str] = set()
        current = start_id
        for _ in range(max_depth):
            if current in visited:
                return True
            visited.add(current)
            c = id_to_concept.get(current)
            if not c or not c.get("parent_id"):
                return False
            current = c["parent_id"]
        return False

    fixed = 0
    for c in concepts:
        if c.get("parent_id") and detect_cycle(c["id"]):
            logger.warning(
                "Cycle detected from '%s', detaching parent", c["label"]
            )
            c["parent_id"] = None
            c["parent_labels"] = []
            fixed += 1

    if fixed:
        logger.info("Detached %d cycle-forming concept(s)", fixed)

    return concepts


def _reconcile_levels(concepts: list[dict]) -> list[dict]:
    """Adjust abstraction levels based on resolved parent relationships.
    
    Only promotes (leaf->branch) or (leaf->root) when structural evidence exists.
    Never demotes a concept that was explicitly assigned root/branch by the model.
    """
    id_to_children: dict[str, list[str]] = {}
    for c in concepts:
        if c.get("parent_id"):
            id_to_children.setdefault(c["parent_id"], []).append(c["id"])

    for c in concepts:
        model_level = c.get("abstraction_level", "branch")
        has_parent = bool(c.get("parent_id"))
        has_children = c["id"] in id_to_children and len(id_to_children[c["id"]]) > 0

        if has_children and not has_parent:
            c["abstraction_level"] = "root"
        elif has_parent and has_children:
            c["abstraction_level"] = "branch"
        elif has_parent and not has_children:
            c["abstraction_level"] = "leaf"
        else:
            # No parent, no children — keep model's original level
            pass

    return concepts


def _build_children(concepts: list[dict]) -> list[dict]:
    """Populate children_ids for each concept."""
    id_to_concept = {c["id"]: c for c in concepts}

    for c in concepts:
        c["children_ids"] = []

    for c in concepts:
        pid = c.get("parent_id")
        if pid and pid in id_to_concept:
            parent = id_to_concept[pid]
            if "children_ids" not in parent:
                parent["children_ids"] = []
            if c["id"] not in parent["children_ids"]:
                parent["children_ids"].append(c["id"])

    return concepts


def _sort_by_importance(concepts: list[dict]) -> list[dict]:
    concepts.sort(key=lambda c: (c.get("importance", 0.5), c.get("confidence", 0.5)), reverse=True)
    return concepts


def assemble_hierarchy(raw_concepts: list[dict]) -> list[dict]:
    if not raw_concepts:
        return []

    logger.info("Starting hierarchy assembly: %d raw concepts", len(raw_concepts))

    # 1. Deduplicate across chunks
    concepts = _deduplicate(raw_concepts)
    logger.info("After dedup: %d concepts", len(concepts))

    # 2. Assign IDs
    concepts = _assign_ids(concepts)

    # 3. Build label-to-ID mapping and resolve parents
    label_to_id = _build_label_to_id(concepts)
    concepts = _resolve_parents(concepts, label_to_id)

    # 4. Ensure acyclicity
    concepts = _ensure_acyclic(concepts)

    # 5. Reconcile abstraction levels
    concepts = _reconcile_levels(concepts)

    # 6. Build children lists
    concepts = _build_children(concepts)

    # 7. Sort by importance and cap
    concepts = _sort_by_importance(concepts)
    concepts = concepts[:MAX_TOTAL_CONCEPTS]

    root_count = sum(1 for c in concepts if c.get("abstraction_level") == "root")
    branch_count = sum(1 for c in concepts if c.get("abstraction_level") == "branch")
    leaf_count = sum(1 for c in concepts if c.get("abstraction_level") == "leaf")
    with_parent = sum(1 for c in concepts if c.get("parent_id"))
    logger.info(
        "Final hierarchy: %d concepts (%d root, %d branch, %d leaf, %d with parent, %d with children)",
        len(concepts), root_count, branch_count, leaf_count, with_parent,
        sum(1 for c in concepts if c.get("children_ids")),
    )

    return concepts
