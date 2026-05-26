from openai import AsyncOpenAI, APIError, APITimeoutError, APIConnectionError
from ..config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

_client: AsyncOpenAI | None = None
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 120


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not DEEPSEEK_API_KEY:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. Create a .env file with your API key."
            )
        _client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


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
