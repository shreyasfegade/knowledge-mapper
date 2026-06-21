import os
import logging
from dotenv import load_dotenv

load_dotenv()


def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key, str(default))
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

BACKEND_HOST: str = os.getenv("BACKEND_HOST", "localhost")
BACKEND_PORT: int = _int_env("BACKEND_PORT", 8000)

# Comma-separated list of allowed CORS origins for the frontend.
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

MAX_UPLOAD_SIZE_MB: int = _int_env("MAX_UPLOAD_SIZE_MB", 50)
MAX_UPLOAD_SIZE_BYTES: int = MAX_UPLOAD_SIZE_MB * 1024 * 1024

MAX_PDF_PAGES: int = _int_env("MAX_PDF_PAGES", 50)
MAX_EXTRACTED_CHARS: int = _int_env("MAX_EXTRACTED_CHARS", 500000)
MAX_CHUNKS: int = _int_env("MAX_CHUNKS", 120)
MAX_TOTAL_CONCEPTS: int = _int_env("MAX_TOTAL_CONCEPTS", 200)

MAX_RESPONSE_TEXT_CHARS: int = _int_env("MAX_RESPONSE_TEXT_CHARS", 100000)

MAX_GLOBAL_CONTEXT_CHARS: int = _int_env("MAX_GLOBAL_CONTEXT_CHARS", 100000)
GLOBAL_UNDERSTANDING_MAX_TOKENS: int = _int_env("GLOBAL_UNDERSTANDING_MAX_TOKENS", 8192)
TOPOLOGY_INFERENCE_MAX_TOKENS: int = _int_env("TOPOLOGY_INFERENCE_MAX_TOKENS", 8192)
MAX_CANDIDATE_PAIRS: int = _int_env("MAX_CANDIDATE_PAIRS", 150)
MAX_RELATIONSHIPS: int = _int_env("MAX_RELATIONSHIPS", 120)
MAX_EDGES_PER_CONCEPT: int = _int_env("MAX_EDGES_PER_CONCEPT", 8)

UPLOAD_DIR: str = os.path.join(os.path.dirname(__file__), "..", "uploads")
DB_PATH: str = os.path.join(os.path.dirname(__file__), "..", "knowledge.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
