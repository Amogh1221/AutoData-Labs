"""
tests/test_llm.py — Unit tests for core/llm.py

Tests cover:
  - CLOUD_MODE=false → uses ollama.chat (not requests)
  - CLOUD_MODE=true, 200 → returns correct dict shape
  - CLOUD_MODE=true, 429 → raises HFKeyExhaustedException
  - CLOUD_MODE=true, other error → raises generic Exception
  - Per-run key override takes priority over env key
  - Thread-local run_id → set_current_run_id / get_run_key wiring
"""

import importlib
import threading
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def reload_llm(env_overrides: dict):
    """Reload core.llm with the given env vars patched."""
    with mock.patch.dict("os.environ", env_overrides, clear=False):
        import core.llm as llm
        importlib.reload(llm)
        return llm


# ---------------------------------------------------------------------------
# Tests: CLOUD_MODE = false (Ollama path)
# ---------------------------------------------------------------------------

class TestOllamaMode:
    def test_delegates_to_ollama_chat(self, monkeypatch):
        """When CLOUD_MODE=false, chat() should call ollama.chat, not requests."""
        import core.llm as llm

        monkeypatch.setenv("CLOUD_MODE", "false")
        fake_response = {"message": {"content": "hello"}}
        mock_ollama = mock.MagicMock(return_value=fake_response)

        with mock.patch("core.llm.ollama") as mock_ol:
            mock_ol.chat.return_value = fake_response
            result = llm.chat(model="llama3", messages=[{"role": "user", "content": "hi"}])

        mock_ol.chat.assert_called_once()
        assert result == fake_response

    def test_passes_format_to_ollama(self, monkeypatch):
        """format kwarg must be forwarded to ollama.chat when set."""
        import core.llm as llm

        monkeypatch.setenv("CLOUD_MODE", "false")
        with mock.patch("core.llm.ollama") as mock_ol:
            mock_ol.chat.return_value = {"message": {"content": "{}"}}
            llm.chat(model="llama3", messages=[], format="json")

        _, kwargs = mock_ol.chat.call_args
        assert kwargs.get("format") == "json" or mock_ol.chat.call_args[1].get("format") == "json" or "json" in str(mock_ol.chat.call_args)


# ---------------------------------------------------------------------------
# Tests: CLOUD_MODE = true (HF path)
# ---------------------------------------------------------------------------

class TestHFMode:
    def _make_response(self, status: int, body: dict):
        resp = mock.MagicMock()
        resp.status_code = status
        resp.json.return_value = body
        resp.text = str(body)
        return resp

    def test_successful_response_shape(self, monkeypatch):
        """200 response is normalised to {message: {content: ...}}."""
        import core.llm as llm

        monkeypatch.setenv("CLOUD_MODE", "true")
        monkeypatch.setenv("HF_API_KEY", "hf_testkey")
        monkeypatch.setenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

        hf_body = {"choices": [{"message": {"content": "extracted data"}}]}
        mock_resp = self._make_response(200, hf_body)

        with mock.patch("core.llm.requests.post", return_value=mock_resp):
            result = llm.chat(model="ignored", messages=[{"role": "user", "content": "hi"}])

        assert result == {"message": {"content": "extracted data"}}

    def test_429_raises_hf_key_exhausted(self, monkeypatch):
        """HTTP 429 must raise HFKeyExhaustedException."""
        import core.llm as llm

        monkeypatch.setenv("CLOUD_MODE", "true")
        monkeypatch.setenv("HF_API_KEY", "hf_testkey")

        mock_resp = self._make_response(429, {"error": "rate limited"})

        with mock.patch("core.llm.requests.post", return_value=mock_resp):
            with pytest.raises(llm.HFKeyExhaustedException):
                llm.chat(model="ignored", messages=[])

    def test_other_error_raises_generic_exception(self, monkeypatch):
        """Non-429 error status should raise a plain Exception."""
        import core.llm as llm

        monkeypatch.setenv("CLOUD_MODE", "true")
        monkeypatch.setenv("HF_API_KEY", "hf_testkey")

        mock_resp = self._make_response(503, {"error": "service unavailable"})

        with mock.patch("core.llm.requests.post", return_value=mock_resp):
            with pytest.raises(Exception) as exc_info:
                llm.chat(model="ignored", messages=[])

        assert "503" in str(exc_info.value)
        assert not isinstance(exc_info.value, llm.HFKeyExhaustedException)

    def test_missing_api_key_raises_value_error(self, monkeypatch):
        """Missing HF_API_KEY in cloud mode should raise ValueError before any HTTP call."""
        import core.llm as llm

        monkeypatch.setenv("CLOUD_MODE", "true")
        monkeypatch.delenv("HF_API_KEY", raising=False)
        # Ensure no run key is set
        llm._run_keys.clear()
        llm._thread_local.run_id = None

        with pytest.raises(ValueError, match="HF_API_KEY"):
            llm.chat(model="ignored", messages=[])


# ---------------------------------------------------------------------------
# Tests: Per-run key management
# ---------------------------------------------------------------------------

class TestRunKeyManagement:
    def test_set_and_get_run_key(self):
        """set_run_key / get_run_key round-trip."""
        import core.llm as llm
        llm.set_run_key("run-abc", "hf_userkey")
        assert llm.get_run_key("run-abc") == "hf_userkey"
        llm.clear_run_key("run-abc")
        assert llm.get_run_key("run-abc") is None

    def test_per_run_key_takes_priority_over_env(self, monkeypatch):
        """User-supplied per-run key should be used instead of env HF_API_KEY."""
        import core.llm as llm

        monkeypatch.setenv("CLOUD_MODE", "true")
        monkeypatch.setenv("HF_API_KEY", "hf_envkey")

        run_id = "run-priority-test"
        llm.set_run_key(run_id, "hf_userkey")
        llm.set_current_run_id(run_id)

        captured_headers = {}

        def fake_post(url, headers, json, timeout):
            captured_headers.update(headers)
            resp = mock.MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
            return resp

        with mock.patch("core.llm.requests.post", side_effect=fake_post):
            llm.chat(model="ignored", messages=[])

        assert captured_headers["Authorization"] == "Bearer hf_userkey"
        llm.clear_run_key(run_id)

    def test_thread_local_run_id_isolation(self):
        """Each thread should have its own run_id without interference."""
        import core.llm as llm

        results = {}

        def worker(run_id):
            llm.set_current_run_id(run_id)
            import time; time.sleep(0.05)
            results[threading.current_thread().name] = getattr(llm._thread_local, "run_id", None)

        t1 = threading.Thread(target=worker, args=("run-1",), name="t1")
        t2 = threading.Thread(target=worker, args=("run-2",), name="t2")
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert results["t1"] == "run-1"
        assert results["t2"] == "run-2"
