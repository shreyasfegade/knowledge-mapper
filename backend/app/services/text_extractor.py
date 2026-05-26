import fitz  # PyMuPDF
from ..config import MAX_PDF_PAGES, MAX_EXTRACTED_CHARS, get_logger

logger = get_logger(__name__)


def extract_text(file_path: str) -> str:
    logger.info("Opening PDF: %s", file_path)

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise ValueError(f"Cannot open PDF (may be corrupt or password-protected): {e}")

    try:
        page_count = doc.page_count
        logger.info("PDF has %d page(s)", page_count)

        if page_count > MAX_PDF_PAGES:
            raise ValueError(
                f"PDF has {page_count} pages, maximum allowed is {MAX_PDF_PAGES}"
            )
        if page_count == 0:
            raise ValueError("PDF contains no pages")

        parts: list[str] = []
        total_chars = 0
        errored_pages = 0

        for page_num, page in enumerate(doc, 1):
            try:
                text = page.get_text("text")
            except Exception:
                errored_pages += 1
                logger.warning("Failed to extract text from page %d, skipping", page_num)
                continue

            if not text:
                continue

            parts.append(text)
            total_chars += len(text)

            if total_chars > MAX_EXTRACTED_CHARS:
                logger.warning(
                    "Truncating at %d chars (limit %d) on page %d",
                    total_chars, MAX_EXTRACTED_CHARS, page_num,
                )
                break

        if errored_pages:
            logger.warning(
                "%d of %d pages failed to extract (possibly images or corrupt objects)",
                errored_pages, page_count,
            )

        result = "\n".join(parts)

        if len(result) > MAX_EXTRACTED_CHARS:
            result = result[:MAX_EXTRACTED_CHARS]

        logger.info("Extracted %d chars from %d page(s)", len(result), page_count)
        return result

    finally:
        doc.close()
