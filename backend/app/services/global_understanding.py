import json
import re
import time
from .deepseek_client import async_chat
from ..config import (
    MAX_GLOBAL_CONTEXT_CHARS,
    GLOBAL_UNDERSTANDING_MAX_TOKENS,
    get_logger,
)

logger = get_logger(__name__)

GLOBAL_SYSTEM = """\
You are an educational analyst. Your task is to build a high-level understanding of what a document teaches.

You are NOT extracting keywords or listing facts. You are building a model of the educational structure of this document.

Read the text and identify:
1. What this document is fundamentally about — synthesize the knowledge it conveys
2. Major thematic threads that run through the material
3. Conceptual domains — distinct knowledge areas the document covers
4. Root concepts — the foundational ideas at the top of the concept hierarchy
5. Educational structure — how the document organizes its teaching
6. Learning flow — the intended progression of understanding

Guidelines:
- Root concepts should be broad, foundational ideas that other concepts build upon. A root concept is something a student must understand before they can grasp finer details. Limit to 3-8 root concepts.
- Domains are distinct knowledge areas. A 50-page document might have 2-5 domains. A short document might have only 1.
- Themes are recurring threads that connect concepts across sections. A theme is not a domain — it's a conceptual thread that weaves through multiple parts of the document.
- The document summary should be a 2-3 paragraph synthesis of what the document teaches, not a table of contents. Describe the knowledge the reader gains.
- Importance scores (0.0-1.0): 0.9+ = central organizing theme, 0.7-0.8 = major focus, 0.5-0.6 = present but secondary, below 0.5 = don't include.
- Domain weights are proportional to how much of the document each domain occupies.

Output as a single JSON object, nothing else:
{
  "document_summary": "2-3 paragraph synthesis...",
  "major_themes": [
    {"name": "Theme Name", "description": "One sentence describing this thematic thread", "importance": 0.85}
  ],
  "conceptual_domains": [
    {"name": "Domain Name", "scope": "What this domain covers in the document", "weight": 0.6, "key_terms": ["term1", "term2"]}
  ],
  "root_concepts": [
    {"name": "Root Concept Name", "definition": "One sentence definition"}
  ],
  "educational_structure": "How the document is organized as a teaching resource",
  "learning_flow": "The intended progression of understanding — what a learner should know first, what builds on what"
}"""


def _parse_global(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse global understanding JSON from: {raw[:500]}")
        try:
            data = json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            raise ValueError(f"JSON in regex match was still malformed: {match.group()[:200]}")

    return data


def _validate_output(data: dict) -> dict:
    required = ["document_summary", "major_themes", "conceptual_domains", "root_concepts", "educational_structure", "learning_flow"]
    for key in required:
        if key not in data:
            logger.warning("Missing key '%s' in global understanding output, using fallback", key)
            if key in ("document_summary", "educational_structure", "learning_flow"):
                data[key] = "Not available."
            elif key == "major_themes":
                data[key] = []
            elif key == "conceptual_domains":
                data[key] = []
            elif key == "root_concepts":
                data[key] = []

    if not isinstance(data.get("major_themes"), list):
        data["major_themes"] = []
    if not isinstance(data.get("conceptual_domains"), list):
        data["conceptual_domains"] = []
    if not isinstance(data.get("root_concepts"), list):
        data["root_concepts"] = []

    for theme in data.get("major_themes", []):
        if not isinstance(theme, dict):
            continue
        theme.setdefault("name", "Unknown Theme")
        theme.setdefault("description", "")
        try:
            theme.setdefault("importance", float(theme.get("importance", 0.5)))
        except (ValueError, TypeError):
            theme["importance"] = 0.5

    for domain in data.get("conceptual_domains", []):
        if not isinstance(domain, dict):
            continue
        domain.setdefault("name", "Unknown Domain")
        domain.setdefault("scope", "")
        try:
            domain.setdefault("weight", float(domain.get("weight", 0.5)))
        except (ValueError, TypeError):
            domain["weight"] = 0.5
        if not isinstance(domain.get("key_terms"), list):
            domain["key_terms"] = []

    for concept in data.get("root_concepts", []):
        if not isinstance(concept, dict):
            continue
        concept.setdefault("name", "Unknown Concept")
        concept.setdefault("definition", "")

    return data


async def async_extract_global_understanding(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("No text provided for global understanding")

    logger.info("Starting global document understanding on %d chars", len(text))

    if len(text) > MAX_GLOBAL_CONTEXT_CHARS:
        logger.info(
            "Truncating text for global understanding: %d -> %d chars",
            len(text), MAX_GLOBAL_CONTEXT_CHARS,
        )
        text = text[:MAX_GLOBAL_CONTEXT_CHARS]

    t_start = time.monotonic()

    raw = await async_chat(
        messages=[
            {"role": "system", "content": GLOBAL_SYSTEM},
            {"role": "user", "content": f"Analyze this educational document and produce a structured understanding:\n\n{text}"},
        ],
        temperature=0.2,
        max_tokens=GLOBAL_UNDERSTANDING_MAX_TOKENS,
    )

    t_end = time.monotonic()
    logger.info(
        "Global understanding response: %d chars in %.1fs",
        len(raw), t_end - t_start,
    )

    data = _parse_global(raw)
    data = _validate_output(data)

    logger.info(
        "Global understanding: %d themes, %d domains, %d root concepts",
        len(data.get("major_themes", [])),
        len(data.get("conceptual_domains", [])),
        len(data.get("root_concepts", [])),
    )

    return data
