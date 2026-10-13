from types import SimpleNamespace

from backend.api import assist_settings
from backend.core import assist_model
from backend.core import local_model_runtime


def test_restart_stops_previous_process_before_starting(monkeypatch):
    calls = []
    monkeypatch.setattr(local_model_runtime, "stop", lambda: calls.append("stop"))
    monkeypatch.setattr(
        local_model_runtime,
        "start",
        lambda config: calls.append(("start", config)) or {"running": True},
    )

    result = local_model_runtime.restart({"modelPath": "model.gguf"})

    assert calls == ["stop", ("start", {"modelPath": "model.gguf"})]
    assert result["running"] is True
    assert "restarted" in result["message"]


def test_admin_runtime_action_routes_restart_to_runtime(monkeypatch):
    calls = []
    monkeypatch.setattr(local_model_runtime, "restart", lambda cfg: calls.append(cfg) or {"ready": False})
    monkeypatch.setattr(assist_model, "configuration", lambda: {"provider": "embedded"})
    request = SimpleNamespace(state=SimpleNamespace(user={"role": "admin"}))

    result = assist_settings.runtime_action("restart", request)

    assert calls == [{"provider": "embedded"}]
    assert result == {"ready": False}
