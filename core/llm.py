"""
core/llm.py — Unified LLM interface supporting Ollama (local) and cloud providers.

Cloud mode is enabled by setting CLOUD_MODE=true in .env.
Set CLOUD_PROVIDER to choose the cloud backend:
  - 'groq'  → Groq API (free tier, fastest, supports Llama 3.1 8B)
  - 'hf'    → Hugging Face router (requires HF credits for gated models)

When the API key is exhausted (HTTP 429), HFKeyExhaustedException is raised so
the pipeline can pause, wait for a user-supplied key, and retry.

Per-run user keys are stored in `_run_keys` (in-memory, never persisted).
The current run_id is propagated via threading.local so services don't need to
pass it explicitly through their call chains.
"""

import os
import threading
import requests
import ollama

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class HFKeyExhaustedException(Exception):
    """Raised when the cloud API returns HTTP 429 (rate limit / quota)."""
    pass

# ---------------------------------------------------------------------------
# Per-run key store (in-memory, session-only)
# ---------------------------------------------------------------------------

_run_keys: dict[str, str] = {}   # run_id → user-supplied API key
_run_keys_lock = threading.Lock()

_thread_local = threading.local()  # stores .run_id for the current worker thread


def set_current_run_id(run_id: str) -> None:
    """Call at the start of each executor thread to bind a run_id to this thread."""
    _thread_local.run_id = run_id


def set_run_key(run_id: str, api_key: str) -> None:
    """Store a user-supplied API key for the given run. Thread-safe."""
    with _run_keys_lock:
        _run_keys[run_id] = api_key


def get_run_key(run_id: str) -> str | None:
    """Return the user-supplied key for this run, or None."""
    with _run_keys_lock:
        return _run_keys.get(run_id)


def clear_run_key(run_id: str) -> None:
    """Remove the user key when the run ends."""
    with _run_keys_lock:
        _run_keys.pop(run_id, None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_openai_compatible(url: str, api_key: str, model: str, messages: list, provider_name: str) -> dict:
    """
    Generic OpenAI-compatible chat completions call.
    Returns { "message": { "content": <str> } }
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 4000,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(
            f"Cannot reach {provider_name} API. "
            f"Check your internet connection or set CLOUD_MODE=false to use local Ollama. "
            f"Detail: {e}"
        ) from e
    except requests.exceptions.Timeout:
        raise TimeoutError(
            f"{provider_name} API timed out after 60 s. "
            f"The model may be loading — try again in a moment, or set CLOUD_MODE=false."
        )

    if response.status_code == 429:
        raise HFKeyExhaustedException(
            f"{provider_name} API quota exhausted (HTTP 429): {response.text[:200]}"
        )

    if response.status_code == 401:
        raise PermissionError(
            f"{provider_name} API key is invalid or expired (HTTP 401). "
            f"Update your API key in .env."
        )

    if response.status_code == 400:
        raise Exception(
            f"{provider_name} API error (HTTP 400) — model '{model}' may not be "
            f"supported. Detail: {response.text[:300]}"
        )

    if response.status_code != 200:
        raise Exception(
            f"{provider_name} API error (HTTP {response.status_code}): {response.text[:200]}"
        )

    data = response.json()
    return {
        "message": {
            "content": data["choices"][0]["message"]["content"]
        }
    }


# ---------------------------------------------------------------------------
# Unified chat function
# ---------------------------------------------------------------------------

def chat(model: str, messages: list, format: str = None) -> dict:
    """
    Drop-in replacement for ollama.chat() that transparently switches between
    local Ollama and a cloud provider depending on CLOUD_MODE / CLOUD_PROVIDER.

    Returns a dict with shape: { "message": { "content": <str> } }

    .env config:
      CLOUD_MODE=true         → enable cloud
      CLOUD_PROVIDER=groq     → use Groq (free, recommended for Llama 3.1)
      CLOUD_PROVIDER=hf       → use Hugging Face router
    """
    cloud_mode = os.getenv("CLOUD_MODE", "false").lower() == "true"

    if not cloud_mode:
        kwargs = {"model": model, "messages": messages}
        if format:
            kwargs["format"] = format
        return ollama.chat(**kwargs)

    cloud_provider = os.getenv("CLOUD_PROVIDER", "groq").lower()

    # Prefer user-supplied per-run key (for API-key-exhaustion recovery flow)
    run_id = getattr(_thread_local, "run_id", None)
    user_key = get_run_key(run_id) if run_id else None

    # ---- Groq path --------------------------------------------------------
    if cloud_provider == "groq":
        api_key = user_key or os.getenv("GROQ_API_KEY")
        if not api_key or api_key in ("your_groq_api_key_here", ""):
            raise ValueError(
                "GROQ_API_KEY is not configured. "
                "Get a free key at https://console.groq.com and add it to .env. "
                "Or set CLOUD_MODE=false to use local Ollama."
            )
        groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        return _call_openai_compatible(
            url="https://api.groq.com/openai/v1/chat/completions",
            api_key=api_key,
            model=groq_model,
            messages=messages,
            provider_name="Groq",
        )

    # ---- Hugging Face path ------------------------------------------------
    if cloud_provider == "hf":
        api_key = user_key or os.getenv("HF_API_KEY")
        if not api_key or api_key == "your_huggingface_api_key_here":
            raise ValueError(
                "HF_API_KEY is not configured. "
                "Set it in your .env file or set CLOUD_MODE=false to use local Ollama."
            )
        hf_model  = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
        # For gated Meta/Llama models use 'nebius'. For open models use 'hf-inference'.
        hf_provider = os.getenv("HF_PROVIDER", "nebius")
        url = f"https://router.huggingface.co/{hf_provider}/v1/chat/completions"
        return _call_openai_compatible(
            url=url,
            api_key=api_key,
            model=hf_model,
            messages=messages,
            provider_name=f"HuggingFace/{hf_provider}",
        )

    raise ValueError(
        f"Unknown CLOUD_PROVIDER='{cloud_provider}'. "
        f"Valid options: 'groq', 'hf'. Set CLOUD_MODE=false to use local Ollama."
    )
