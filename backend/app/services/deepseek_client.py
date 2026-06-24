from contextvars import ContextVar

from openai import AsyncOpenAI, APIError, APITimeoutError, APIConnectionError
from ..config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 120

# Per-request API key override. The upload handler sets this from an X-API-Key
# header so a visitor can process a PDF with their own key (bring-your-own-key),
# without the server needing one. Falls back to the server's env key when unset.
current_api_key: ContextVar[str | None] = ContextVar("km_current_api_key", default=None)

# One client per distinct key, reused across requests.
_clients: dict[str, AsyncOpenAI] = {}


def _resolve_key() -> str:
    return (current_api_key.get() or DEEPSEEK_API_KEY or "").strip()


def has_api_key() -> bool:
    """True when an effective key is available (server env or per-request override)."""
    return bool(_resolve_key())


def server_has_key() -> bool:
    """True when the server itself is configured with a key (ignores per-request)."""
    return bool((DEEPSEEK_API_KEY or "").strip())


def _get_client() -> AsyncOpenAI:
    key = _resolve_key()
    if not key:
        raise RuntimeError(
            "No API key available. Set DEEPSEEK_API_KEY on the server, or provide "
            "your own DeepSeek/OpenAI-compatible key with the request."
        )
    client = _clients.get(key)
    if client is None:
        client = AsyncOpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
        _clients[key] = client
    return client


async def async_chat(
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    try:
        response = await _get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    except APITimeoutError:
        raise RuntimeError(
            f"DeepSeek API timed out after {timeout}s. The text chunk may be too large "
            "or the API is experiencing high load."
        )
    except APIConnectionError as e:
        raise RuntimeError(
            f"Cannot connect to DeepSeek API at {DEEPSEEK_BASE_URL}. "
            f"Check your network and DEEPSEEK_BASE_URL setting. Details: {e}"
        )
    except APIError as e:
        raise RuntimeError(
            f"DeepSeek API error (status {e.status_code}): {e.message}"
        )

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("DeepSeek returned empty response (no content)")
    return content
