import re
from ..config import MAX_EXTRACTED_CHARS, get_logger

logger = get_logger(__name__)


def clean_text(raw: str) -> str:
    initial_len = len(raw)
    logger.info("Cleaning text (%d chars)", initial_len)

    if initial_len > MAX_EXTRACTED_CHARS:
        raw = raw[:MAX_EXTRACTED_CHARS]
        logger.warning("Truncated input to %d chars before cleaning", MAX_EXTRACTED_CHARS)

    # Remove page break artifacts (hyphenated line breaks)
    text = re.sub(r"-\n(\S)", r"\1", raw)

    # Remove common header/footer patterns (page numbers, repeated headers)
    # Patterns like "Page 3 of 45", "- 3 -", standalone numbers on lines
    text = re.sub(r"^(?:page\s+)?\d+(?:\s+of\s+\d+)?\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^-\s*\d+\s*-\s*$", "", text, flags=re.MULTILINE)

    # Remove bullet/list artifacts that are just symbols on their own line
    text = re.sub(r"^[•·▪▸►◆◇○●■□→»]\s*$", "", text, flags=re.MULTILINE)

    # Remove repeated section dividers
    text = re.sub(r"^[=_\-─]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Remove common OCR artifacts (stray control chars, non-printable chars)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize unicode quotes and dashes
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u00a0", " ")  # non-breaking space

    # Collapse multiple blank lines to single newline
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip leading/trailing whitespace per line
    text = "\n".join(line.strip() for line in text.splitlines())

    # Remove repeated non-breaking spaces and other artifacts
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Remove lines that are just short fragments (likely artifacts)
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Keep empty lines (paragraph breaks), but remove very short noise lines
        if not stripped:
            cleaned_lines.append("")
        elif len(stripped) >= 3 or re.match(r"^[A-Z]", stripped):
            # Keep lines ≥ 3 chars or starting with capital (likely headings)
            cleaned_lines.append(line)
        # else: drop short noise fragments

    text = "\n".join(cleaned_lines)

    # Final collapse of excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim overall whitespace
    text = text.strip()

    logger.info("Cleaned: %d -> %d chars", initial_len, len(text))
    return text
