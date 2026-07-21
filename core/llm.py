"""
core/llm.py — Unified LLM interface supporting Ollama (local) and Hugging Face (cloud).

Cloud mode is enabled by setting CLOUD_MODE=true in .env.
When the HF API key is exhausted (HTTP 429), HFKeyExhaustedException is raised so
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
    """Raised when the HF Inference API returns HTTP 429 (rate limit / quota)."""
    pass

# ---------------------------------------------------------------------------
# Per-run key store (in-memory, session-only)
# ---------------------------------------------------------------------------

_run_keys: dict[str, str] = {}   # run_id → user-supplied HF API key
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
# Unified chat function
# ---------------------------------------------------------------------------

def chat(model: str, messages: list, format: str = None) -> dict:
    """
    Drop-in replacement for ollama.chat() that transparently switches between
    local Ollama and the HF Inference API depending on CLOUD_MODE.

    Returns a dict with shape: { "message": { "content": <str> } }
    """
    cloud_mode = os.getenv("CLOUD_MODE", "false").lower() == "true"

    if not cloud_mode:
        kwargs = {"model": model, "messages": messages}
        if format:
            kwargs["format"] = format
        return ollama.chat(**kwargs)

    # --- Cloud (Hugging Face) path ---
    # Prefer user-supplied per-run key, fall back to .env key
    run_id = getattr(_thread_local, "run_id", None)
    api_key = (get_run_key(run_id) if run_id else None) or os.getenv("HF_API_KEY")

    if not api_key or api_key == "your_huggingface_api_key_here":
        raise ValueError(
            "HF_API_KEY is not configured. "
            "Set it in your .env file or set CLOUD_MODE=false to use local Ollama."
        )

    hf_model = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    # HF migrated from api-inference.huggingface.co → router.huggingface.co in 2025
    url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": hf_model,
        "messages": messages,
        "max_tokens": 4000,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(
            f"Cannot reach Hugging Face API ({hf_model}). "
            f"Check your internet connection or set CLOUD_MODE=false to use local Ollama. "
            f"Detail: {e}"
        ) from e
    except requests.exceptions.Timeout:
        raise TimeoutError(
            f"Hugging Face API timed out after 60 s. "
            f"The model may be loading — try again in a moment, or set CLOUD_MODE=false."
        )

    if response.status_code == 429:
        raise HFKeyExhaustedException(
            f"Hugging Face API quota exhausted (HTTP 429): {response.text[:200]}"
        )

    if response.status_code == 401:
        raise PermissionError(
            f"Hugging Face API key is invalid or expired (HTTP 401). "
            f"Update HF_API_KEY in your .env file."
        )

    if response.status_code != 200:
        raise Exception(
            f"Hugging Face API error (HTTP {response.status_code}): {response.text[:200]}"
        )

    data = response.json()
    return {
        "message": {
            "content": data["choices"][0]["message"]["content"]
        }
    }

