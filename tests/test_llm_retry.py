"""Transient Gemini retry behavior (Phase 5 polish)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services import llm as llm_mod


def test_is_transient_llm_error_detects_rate_limits() -> None:
    assert llm_mod._is_transient_llm_error(RuntimeError("429 Resource exhausted"))
    assert llm_mod._is_transient_llm_error(RuntimeError("Service Unavailable 503"))
    assert not llm_mod._is_transient_llm_error(RuntimeError("InvalidArgument: bad prompt"))


def test_generate_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("GEMINI_RETRY_BASE_DELAY_SEC", "0")

    ok = MagicMock()
    ok.text = "ok-response"
    ok.candidates = None

    model = MagicMock()
    model.generate_content.side_effect = [
        RuntimeError("429 rate limit"),
        ok,
    ]

    with (
        patch.object(llm_mod, "_init_vertex"),
        patch("vertexai.generative_models.GenerativeModel", return_value=model),
        patch.object(llm_mod.time, "sleep") as sleep_mock,
    ):
        text = llm_mod._generate("gemini-1.5-flash", "hello")

    assert text == "ok-response"
    assert model.generate_content.call_count == 2
    sleep_mock.assert_called_once()


def test_generate_raises_after_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("GEMINI_RETRY_BASE_DELAY_SEC", "0")

    model = MagicMock()
    model.generate_content.side_effect = RuntimeError("503 unavailable")

    with (
        patch.object(llm_mod, "_init_vertex"),
        patch("vertexai.generative_models.GenerativeModel", return_value=model),
        patch.object(llm_mod.time, "sleep"),
        pytest.raises(llm_mod.LlmServiceError, match="failed"),
    ):
        llm_mod._generate("gemini-1.5-flash", "hello")

    assert model.generate_content.call_count == 2
