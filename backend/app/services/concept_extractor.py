import json
import re
import time
import asyncio
from .deepseek_client import async_chat
from ..config import MAX_CHUNKS, MAX_TOTAL_CONCEPTS, get_logger

logger = get_logger(__name__)

MAX_CHUNK_CHARS = 10000
CHUNK_OVERLAP_CHARS = 300

HIERARCHICAL_EXTRACTION_SYSTEM = """\
You are an expert educational knowledge architect. Your task is to extract the meaningful conceptual structure from academic text — the ideas a learner needs to understand, organized into a coherent hierarchy.

You are NOT listing keywords or terms. You are identifying the knowledge units that a teacher would write on a whiteboard when explaining this material. Every concept you extract should be something that can be taught and understood as a distinct idea.

─── CONCEPT QUALITY HEURISTICS ───

A good concept:
- Can be explained in 1-2 paragraphs to a student
- Has a clear, non-trivial definition (not just a word)
- Is discussed substantively in the text (at least a sentence of explanation)
- Would appear in a well-organized lecture outline

A bad concept (DO NOT extract these):
- A single keyword with no explained meaning
- A vague category ("Important Topics", "Key Concepts")
- A proper noun mentioned in passing (a cited author, a specific company)
- A concept identical to another already extracted (merge duplicates)
- A definition that is just a rephrasing of the label

─── CLASSIFICATION FIELDS ───

CONCEPT TYPE — what kind of knowledge:
- "foundation" — Bedrock concept that others build upon. E.g. "Crystal Structure", "Newton's Second Law"
- "mechanism" — Causal chain or process that explains HOW something works. E.g. "Hall-Petch Strengthening", "Osmotic Pressure Regulation"
- "process" — A procedure, method, or sequence of steps. E.g. "Annealing", "PCR Amplification"
- "application" — Practical use of theoretical concepts. E.g. "Hardness Testing", "Spectrophotometry"
- "abstraction" — Unifying principle, theory, or model. E.g. "Phase Diagrams", "Natural Selection"
- "derived" — Concept whose meaning depends on other concepts. E.g. "Critical Cooling Rate", "Activation Energy"

ABSTRACTION LEVEL — position in knowledge hierarchy:
- "root" — Top of a conceptual branch. Broad, foundational. No parent in this document.
- "branch" — Intermediate. Has both parent and children concepts.
- "leaf" — Terminal. Specific, no sub-concepts below it in this document.

EDUCATIONAL ROLE:
- "central" — Core to the document's teaching purpose. Remove it and comprehension collapses.
- "supporting" — Important context but not blocking.
- "detail" — Narrow fact, example, or edge case. Non-essential.

─── HIERARCHY RULES ───

parent_labels: The concept label(s) this falls under. At most one parent. Root concepts have [].
prerequisite_labels: Concepts the learner MUST understand BEFORE this one. Be conservative — only flag clear cognitive dependencies, not loose thematic associations.

─── OUTPUT RULES ───

- Extract 10-20 concepts per chunk. Capture every meaningful knowledge unit thoroughly. More is better than fewer, as long as each concept has real substance and educational value.
- Labels: 2-7 words. Specific and descriptive. "Martensitic Phase Transformation" not "Transformation".
- Summaries: 1-2 sentences explaining what the concept IS and WHY it matters. Never just restate the label.
- Confidence: Your confidence that this is a real, well-discussed concept (not a namedrop). 0.9+ = extensively discussed, 0.5 = barely mentioned.
- Importance: How central this concept is to the document. 0.9+ = essential, 0.5 = peripheral.
- Domain and theme: Match to the global context. Pick the single best-fit domain and theme.

─── ANTI-PATTERNS (EXPLICITLY BANNED) ───

Do NOT produce concepts like:
- "Introduction" / "Summary" / "Conclusion" — these are document sections, not concepts
- "Key Terms" / "Important Concepts" — meta-labels, not knowledge
- "Figure 3.2" / "Table 1" — artifacts, not concepts
- Any concept whose summary is just "This is [label]" or "[label] is discussed in the text"
- Two concepts that mean the same thing (e.g. "Cooling Rate" and "Rate of Cooling")

Output as a single JSON object with a "concepts" array, nothing else:
{
  "concepts": [
    {
      "label": "Quenching",
      "summary": "Rapid cooling of a metal from elevated temperature to produce martensite — a hard but brittle microstructure. Quench severity depends on the cooling medium and agitation, controlling whether the material achieves full hardening.",
      "confidence": 0.95,
      "concept_type": "process",
      "abstraction_level": "branch",
      "educational_role": "central",
      "importance": 0.9,
      "parent_labels": ["Heat Treatment"],
      "domain": "Heat Treatment Processes",
      "theme": "Process-Property Relationships",
      "prerequisite_labels": ["Phase Transformations"]
    }
  ]
}"""


def _build_global_context(global_understanding: dict) -> str:
    """Build a concise context string from Stage 1 output for the extraction prompt."""
    parts: list[str] = []

    summary = global_understanding.get("document_summary", "")
    if summary:
        parts.append(f"DOCUMENT SUMMARY: {summary}")

    roots = global_understanding.get("root_concepts", [])
    if roots:
        names = [rc.get("name", "?") for rc in roots]
        parts.append(f"ROOT CONCEPTS (top of hierarchy): {', '.join(names)}")

    domains = global_understanding.get("conceptual_domains", [])
    if domains:
        domain_lines = [
            f"- {d.get('name', '?')}: {d.get('scope', '')[:100]}"
            for d in domains
        ]
        parts.append(f"CONCEPTUAL DOMAINS:\n" + "\n".join(domain_lines))

    themes = global_understanding.get("major_themes", [])
    if themes:
        theme_lines = [
            f"- {t.get('name', '?')}" for t in themes
        ]
        parts.append(f"MAJOR THEMES:\n" + "\n".join(theme_lines))

    flow = global_understanding.get("learning_flow", "")
    if flow:
        parts.append(f"LEARNING FLOW: {flow}")

    return "\n\n".join(parts)


def _parse_concepts(raw: str) -> list[dict]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse concept JSON from: {raw[:300]}")
        try:
            data = json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            raise ValueError(f"JSON in regex match was still malformed: {match.group()[:200]}")

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "concepts" in data:
        return data["concepts"]
    raise ValueError(f"Expected JSON object with 'concepts' array, got: {type(data)}")


def _validate_concept(c: dict) -> dict:
    allowed_types = {"foundation", "mechanism", "process", "application", "abstraction", "derived"}
    allowed_levels = {"root", "branch", "leaf"}
    allowed_roles = {"central", "supporting", "detail"}

    concept_type = str(c.get("concept_type", "")).strip().lower()
    if concept_type not in allowed_types:
        concept_type = "process"

    level = str(c.get("abstraction_level", "")).strip().lower()
    if level not in allowed_levels:
        level = "branch"

    role = str(c.get("educational_role", "")).strip().lower()
    if role not in allowed_roles:
        role = "supporting"

    try:
        importance = float(c.get("importance", 0.5))
        importance = max(0.0, min(1.0, importance))
    except (ValueError, TypeError):
        importance = 0.5

    try:
        confidence = float(c.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.5

    parent_labels = c.get("parent_labels", [])
    if not isinstance(parent_labels, list):
        parent_labels = []
    parent_labels = [str(p).strip() for p in parent_labels if str(p).strip()]

    prereq_labels = c.get("prerequisite_labels", [])
    if not isinstance(prereq_labels, list):
        prereq_labels = []
    prereq_labels = [str(p).strip() for p in prereq_labels if str(p).strip()]

    return {
        "label": str(c.get("label", "")).strip(),
        "summary": str(c.get("summary", "")).strip(),
        "confidence": confidence,
        "concept_type": concept_type,
        "abstraction_level": level,
        "educational_role": role,
        "importance": importance,
        "parent_labels": parent_labels,
        "domain": str(c.get("domain", "")).strip(),
        "theme": str(c.get("theme", "")).strip(),
        "prerequisite_labels": prereq_labels,
    }


def _chunk_text(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len and len(chunks) < MAX_CHUNKS:
        end = min(start + MAX_CHUNK_CHARS, text_len)
        chunks.append(text[start:end])

        if end >= text_len:
            break

        start = end - CHUNK_OVERLAP_CHARS

    if len(chunks) >= MAX_CHUNKS:
        logger.warning("Hit max chunk limit (%d), stopped chunking", MAX_CHUNKS)

    logger.info(
        "Chunked %d chars -> %d chunks (sizes: %s)",
        text_len,
        len(chunks),
        [len(c) for c in chunks],
    )
    return chunks


async def _process_chunk(
    chunk: str, i: int, total: int, global_context: str, semaphore: asyncio.Semaphore, update_progress=None
) -> list[dict]:
    """Process a single text chunk through the LLM asynchronously."""
    async with semaphore:
        t_chunk_start = time.monotonic()
        logger.info(
            "DeepSeek request %d/%d (chunk size: %d chars)",
            i + 1, total, len(chunk),
        )
        header = f"Text excerpt {i + 1} of {total}:\n\n" if total > 1 else ""

        context_block = ""
        if global_context:
            context_block = f"Global context for this document:\n{global_context}\n\nUse this context to determine concept types, hierarchy placement, and domain/theme assignments.\n\n"

        user_prompt = f"{context_block}{header}{chunk}"

        try:
            raw = await async_chat(
                messages=[
                    {"role": "system", "content": HIERARCHICAL_EXTRACTION_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except Exception as e:
            logger.error("Failed to process chunk %d/%d: %s", i + 1, total, e)
            if update_progress:
                update_progress()
            return []

        t_chunk_end = time.monotonic()
        logger.info(
            "DeepSeek response %d/%d: %d chars in %.1fs",
            i + 1, total, len(raw), t_chunk_end - t_chunk_start,
        )

        try:
            parsed = _parse_concepts(raw)
        except ValueError as e:
            logger.warning("Failed to parse concepts for chunk %d: %s", i + 1, e)
            if update_progress:
                update_progress()
            return []

        valid_concepts = []
        for c in parsed:
            if not isinstance(c, dict):
                continue
            validated = _validate_concept(c)
            if validated["confidence"] >= 0.5 and validated["label"]:
                valid_concepts.append(validated)

        logger.info("Chunk %d yielded %d concept(s)", i + 1, len(valid_concepts))
        
        if update_progress:
            update_progress()
            
        return valid_concepts


async def async_extract_concepts(
    text: str, global_understanding: dict | None = None, status_callback=None
) -> list[dict]:
    text = text.strip()
    if not text:
        raise ValueError("No text provided for concept extraction")

    logger.info("Starting hierarchical concept extraction on %d chars", len(text))

    global_context = ""
    if global_understanding:
        global_context = _build_global_context(global_understanding)
        logger.info("Global context length: %d chars", len(global_context))

    chunks = _chunk_text(text)
    
    completed_chunks = 0
    total_chunks = len(chunks)
    
    def update_progress():
        nonlocal completed_chunks
        completed_chunks += 1
        if status_callback:
            status_callback(f"Extracting concepts ({completed_chunks}/{total_chunks})")

    # Use a semaphore to limit concurrent LLM requests to avoid rate limiting
    semaphore = asyncio.Semaphore(10)
    
    tasks = [
        _process_chunk(chunk, i, total_chunks, global_context, semaphore, update_progress)
        for i, chunk in enumerate(chunks)
    ]
    
    results = await asyncio.gather(*tasks)
    
    raw_concepts: list[dict] = []
    for chunk_concepts in results:
        raw_concepts.extend(chunk_concepts)

    if len(raw_concepts) >= MAX_TOTAL_CONCEPTS * 2:
        logger.info("Reached pre-dedup cap (%d), truncating", MAX_TOTAL_CONCEPTS * 2)
        raw_concepts = raw_concepts[:MAX_TOTAL_CONCEPTS * 2]

    logger.info("Raw concepts before hierarchy assembly: %d", len(raw_concepts))
    return raw_concepts
