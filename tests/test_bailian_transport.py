from urllib.error import HTTPError

import pytest

from tracerepair.model_planner import BailianChatTransport, PlannerError


def test_http_rejection_reports_only_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args, **_kwargs):
        raise HTTPError("https://example.invalid", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("tracerepair.model_planner.urlopen", reject)
    transport = BailianChatTransport(api_key="not-a-real-key", base_url="https://example.invalid")

    with pytest.raises(PlannerError, match="HTTP 401") as error:
        transport.complete({"model": "qwen-coder-turbo"})

    assert "not-a-real-key" not in str(error.value)


def test_http_rejection_keeps_short_safe_provider_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def read(self) -> bytes:
            return b'{"message":"model missing; supplied sk-secret-value"}'

    def reject(*_args, **_kwargs):
        raise HTTPError("https://example.invalid", 404, "Not Found", {}, Response())

    monkeypatch.setattr("tracerepair.model_planner.urlopen", reject)
    transport = BailianChatTransport(api_key="not-a-real-key", base_url="https://example.invalid")

    with pytest.raises(PlannerError) as error:
        transport.complete({"model": "qwen-turbo"})

    assert "model missing" in str(error.value)
    assert "sk-secret-value" not in str(error.value)
