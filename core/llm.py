"""Shared Groq OpenAI-compatible client with deterministic retry handling."""
import re
import time
from openai import APIConnectionError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError
from core.config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
        _client = OpenAI(base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY)
    return _client


def _seconds_to_wait(error: RateLimitError) -> float:
    try:
        value = error.response.headers.get("retry-after")
        if value:
            return float(value)
    except Exception:
        pass
    match = re.search(r"try again in ([\d.]+)s", str(error), re.IGNORECASE)
    return float(match.group(1)) if match else 20.0


def call_llm(prompt: str, max_tokens: int = 2048, model: str | None = None, reasoning_effort: str = "low", max_retries: int = 3) -> str:
    client = _get_client()
    response = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(model=model or GROQ_MODEL, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, reasoning_effort=reasoning_effort)
            break
        except AuthenticationError as error:
            raise RuntimeError(f"Groq rejected the API key. Check GROQ_API_KEY. Original error: {error}") from error
        except RateLimitError as error:
            if attempt == max_retries:
                raise RuntimeError(f"Groq rate limit hit {max_retries + 1} times. Original error: {error}") from error
            time.sleep(_seconds_to_wait(error))
        except (APIConnectionError, APITimeoutError) as error:
            if attempt == max_retries:
                raise RuntimeError(f"Could not reach Groq after {max_retries + 1} attempts. Original error: {error}") from error
            time.sleep(5.0)
    if response is None:
        raise RuntimeError("No response returned by Groq.")
    choice = response.choices[0]
    content = choice.message.content
    finish_reason = getattr(choice, "finish_reason", "unknown")
    if not content:
        raise RuntimeError(f"Groq returned empty content (finish_reason={finish_reason}). Increase max_tokens or lower reasoning_effort.")
    if finish_reason == "length":
        raise RuntimeError(f"Groq response was truncated after max_tokens={max_tokens}.")
    return content
