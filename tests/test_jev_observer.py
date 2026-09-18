from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from harness_core import jev_observer as observer
from harness_core.sensor_evidence import refresh_sensor_mirror, resolve_sensor_evidence


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path.resolve()
    run = root / ".harness/runs/TASK-001/run-001"
    run.mkdir(parents=True)
    settings = {"enabled": True, "mode": "shadow", "allow_remote_state": True, "min_interval_seconds": 1}
    write(root / ".harness/config.json", {"jev_observer": settings})
    write(root / ".harness/contracts/TASK-001.json", {"goal": "Corrigir cadastro", "required_sensors": ["python -m pytest"]})
    write(run / "run.json", {"task_id": "TASK-001", "run_id": run.name})
    write(root / ".harness/tasks/index.json", {"tasks": [{"task_id": "TASK-001", "status": "working"}]})
    (root / "app.py").write_text("print('original')\n", encoding="utf-8")
    monkeypatch.setattr(observer, "source_identity", lambda path: hashlib.sha256((path / "app.py").read_bytes()).hexdigest())
    return root, run, settings


def sensor(run: Path, tier: str = "full", minute: int = 1, passed: bool = False) -> dict:
    return {"task_id": "TASK-001", "run_dir": str(run), "tier": tier,
            "created_at": f"2026-09-18T12:{minute:02d}:00+00:00", "passed": passed,
            "results": [{"command": "python -m pytest", "exit_code": 0 if passed else 1,
                         "stderr": "Connection refused", "stdout": ""}]}


def fake(request: dict, timeout: float) -> dict:
    assert timeout > 0
    return {"request_id": request["request_id"], "answers": {
        "repeated_failure": {"probability": 0.9},
        "environment_blocker": {"probability": 0.95},
        "insufficient_evidence": {"probability": 0.1},
    }}


def test_disabled_does_not_collect_call_or_write(project, monkeypatch):
    root, run, _ = project
    write(root / ".harness/config.json", {})
    monkeypatch.setattr(observer, "collect_state", lambda *_: pytest.fail("collected while disabled"))
    result = observer.observe(root, run, transport=lambda *_: pytest.fail("called while disabled"))
    assert result["status"] == "disabled"
    assert not (run / "jev").exists()


@pytest.mark.parametrize("changes", [{"allow_remote_state": False}, {"enabled": "true"}, {"mode": "autonomous"}])
def test_explicit_boolean_consent_and_shadow_only(project, changes):
    root, run, settings = project
    write(root / ".harness/config.json", {"jev_observer": {**settings, **changes}})
    result = observer.observe(root, run, transport=lambda *_: pytest.fail("should not call"))
    assert result["status"] in {"disabled", "unavailable"}
    assert result["applied"] is False


def test_observation_never_changes_task_contract_or_code(project):
    root, run, _ = project
    write(run / "sensors-full.json", sensor(run))
    protected = [root / "app.py", root / ".harness/tasks/index.json", root / ".harness/contracts/TASK-001.json"]
    before = {path: path.read_bytes() for path in protected}
    result = observer.observe(root, run, transport=fake)
    assert result["status"] == "observed"
    assert result["applied"] is False
    assert "Possível bloqueio" in result["recommendation"]
    assert before == {path: path.read_bytes() for path in protected}
    assert not (run / "evaluation.json").exists()
    assert observer.current_observation(root, run)["status"] == "observed"


@pytest.mark.parametrize("mutate", ["code", "contract", "sensors", "config"])
def test_late_answers_are_discarded(project, mutate):
    root, run, settings = project
    write(run / "sensors-full.json", sensor(run))
    def transport(request, timeout):
        if mutate == "code":
            (root / "app.py").write_text("uncommitted change", encoding="utf-8")
        elif mutate == "contract":
            write(root / ".harness/contracts/TASK-001.json", {"goal": "changed"})
        elif mutate == "config":
            write(root / ".harness/config.json", {"jev_observer": {**settings, "enabled": False}})
        else:
            write(run / "sensors-full.json", sensor(run, minute=2))
        return fake(request, timeout)
    result = observer.observe(root, run, transport=transport)
    assert result["status"] == "stale"
    assert "recommendation" not in result
    assert result["applied"] is False


def test_status_does_not_present_old_advice_as_current(project):
    root, run, _ = project
    observer.observe(root, run, transport=fake)
    (root / "app.py").write_text("changed", encoding="utf-8")
    result = observer.current_observation(root, run)
    assert result["status"] == "stale"
    assert "recommendation" not in result


@pytest.mark.parametrize("value", [-1, 2, True, "0.95", None, float("nan"), float("inf")])
def test_malformed_probability_is_rejected(project, value):
    root, run, _ = project
    def transport(request, timeout):
        response = fake(request, timeout)
        response["answers"]["repeated_failure"]["probability"] = value
        return response
    result = observer.observe(root, run, transport=transport)
    assert result["status"] == "unavailable"
    assert "recommendation" not in result


def test_wrong_request_id_is_rejected(project):
    root, run, _ = project
    result = observer.observe(root, run, transport=lambda *_: {"request_id": "wrong", "answers": {}})
    assert result["status"] == "unavailable"


def test_timeout_is_counted_and_does_not_leak_error(project):
    root, run, settings = project
    write(root / ".harness/config.json", {"jev_observer": {**settings, "max_calls_per_run": 1}})
    def fail(*_):
        raise subprocess.TimeoutExpired("private-credential-do-not-log", 1)
    result = observer.observe(root, run, transport=fail)
    assert result["status"] == "unavailable"
    assert "private-credential" not in (run / "jev/latest.json").read_text(encoding="utf-8")
    assert observer.observe(root, run, transport=fake)["reason"] == "call_budget"


def test_busy_lock_skips_observation(project):
    root, run, _ = project
    (run / "jev").mkdir()
    (run / "jev/.observer.lock").touch()
    result = observer.observe(root, run, transport=lambda *_: pytest.fail("busy"))
    assert result["reason"] == "observer_busy"


def test_cooldown_and_deduplication(project, monkeypatch):
    root, run, _ = project
    observer.observe(root, run, transport=fake)
    assert observer.observe(root, run, transport=fake)["reason"] == "cooldown"
    now = observer.time.time()
    monkeypatch.setattr(observer.time, "time", lambda: now + 5)
    assert observer.observe(root, run, transport=lambda *_: pytest.fail("duplicate"))["reason"] == "unchanged_state"


def test_unavailable_can_retry_after_cooldown(project, monkeypatch):
    root, run, _ = project
    observer.observe(root, run, transport=lambda *_: {})
    now = observer.time.time()
    monkeypatch.setattr(observer.time, "time", lambda: now + 5)
    assert observer.observe(root, run, transport=fake)["status"] == "observed"


@pytest.mark.parametrize("setting,value", [("timeout_seconds", -1), ("max_calls_per_run", 1.5), ("signal_threshold", True)])
def test_invalid_configuration_never_calls_provider(project, setting, value):
    root, run, settings = project
    write(root / ".harness/config.json", {"jev_observer": {**settings, setting: value}})
    assert observer.observe(root, run, transport=lambda *_: pytest.fail("invalid config"))["status"] == "unavailable"


def test_redaction_precedes_truncation(project, monkeypatch):
    root, run, _ = project
    secret = "my-private-gateway-credential"
    monkeypatch.setenv("AI_GATEWAY_API_KEY", secret)
    data = sensor(run)
    data["results"][0]["stderr"] = f"{secret} password=do-not-show https://user:pass@host/db Bearer abcdefgh"
    write(run / "sensors-full.json", data)
    state = json.dumps(observer.collect_state(root, run))
    for value in [secret, "do-not-show", "user:pass", "abcdefgh"]:
        assert value not in state
    assert "REDACTED" in state
    assert secret[-5:] not in observer._redact(secret, 5)


def test_raw_headers_and_private_keys_are_redacted():
    text = "Cookie: session=do-not-show; other=also-private\n-----BEGIN PRIVATE KEY-----\nprivate-body\n-----END PRIVATE KEY-----"
    assert "do-not-show" not in observer._redact(text)
    assert "also-private" not in observer._redact(text)
    assert "private-body" not in observer._redact(text)


def test_checkpoints_are_scoped_deduplicated_and_bounded(project):
    root, run, _ = project
    first, second = sensor(run), sensor(run, minute=2)
    checkpoints = root / ".harness/checkpoints/TASK-001"
    for name, data in [("01", first), ("02", first), ("03", second)]:
        write(checkpoints / f"checkpoint-{name}.json", {"task_id": "TASK-001", "run_dir": str(run), "sensors": data})
    write(checkpoints / "checkpoint-04.json", {"task_id": "TASK-001", "run_dir": "other-run", "sensors": sensor(run, minute=3)})
    write(run / "sensors-full.json", second)
    state = observer.collect_state(root, run)
    assert len(state["attempts"]) == 2
    assert len(json.dumps(state).encode()) < observer.MAX_REQUEST_BYTES


def test_preview_never_contacts_gateway(project, monkeypatch, capsys):
    root, _, _ = project
    monkeypatch.setattr(observer, "gateway_transport", lambda *_: pytest.fail("preview contacted gateway"))
    assert observer.main(["--repo", str(root), "--task", "TASK-001"]) == 0
    assert json.loads(capsys.readouterr().out)["network"] is False


def test_path_traversal_is_rejected(project):
    root, _, _ = project
    assert observer.main(["--repo", str(root), "--task", "../outside"]) == 2


def test_symlink_ledger_cannot_overwrite_task_state(project):
    root, run, _ = project
    target = root / ".harness/tasks"
    try:
        (run / "jev").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    before = (target / "index.json").read_bytes()
    assert observer.observe(root, run, transport=lambda *_: pytest.fail("symlink"))["status"] == "unavailable"
    assert (target / "index.json").read_bytes() == before


def test_newer_all_failure_beats_old_full_success_and_mirror(project):
    root, run, _ = project
    full, all_sensors = sensor(run, passed=True), sensor(run, tier="all", minute=2)
    write(run / "sensors-full.json", full)
    write(run / "sensors-all.json", all_sensors)
    write(run / "sensors.json", full)
    contract = {"required_sensors": ["python -m pytest"]}
    assert resolve_sensor_evidence(run, contract) == all_sensors
    refresh_sensor_mirror(root, run)
    assert json.loads((run / "sensors.json").read_text()) == all_sensors


def test_newer_full_beats_old_all(project):
    _, run, _ = project
    write(run / "sensors-all.json", sensor(run, tier="all"))
    latest = sensor(run, minute=2, passed=True)
    write(run / "sensors-full.json", latest)
    assert resolve_sensor_evidence(run, {"required_sensors": ["test"]}) == latest


def test_quick_tier_cannot_satisfy_final_contract(project):
    root, run, _ = project
    write(run / "sensors-smoke.json", sensor(run, tier="smoke", passed=True))
    write(run / "sensors.json", sensor(run, tier="smoke", passed=True))
    assert resolve_sensor_evidence(run, {"required_sensors": ["test"]}) == {}
    refresh_sensor_mirror(root, run)
    assert json.loads((run / "sensors.json").read_text())["tier"] == "smoke"
    assert resolve_sensor_evidence(run, {"required_sensors": ["test"]}) == {}


def test_corrupt_newest_evidence_does_not_fall_back_to_pass(project):
    _, run, _ = project
    data = sensor(run, passed=True)
    data["created_at"] = "2001-01-01T00:00:00+00:00"
    write(run / "sensors-full.json", data)
    (run / "sensors-all.json").write_text("not json", encoding="utf-8")
    assert resolve_sensor_evidence(run, {"required_sensors": ["test"]})["passed"] is False


def test_wrong_run_evidence_is_nonpassing(project):
    _, run, _ = project
    data = sensor(run, passed=True)
    data["run_dir"] = str(run.parent / "other")
    write(run / "sensors-full.json", data)
    assert resolve_sensor_evidence(run, {"required_sensors": ["test"]})["evidence_error"] == "wrong_run"


def test_legacy_evidence_remains_readable(tmp_path):
    data = {"tier": "smoke", "passed": True}
    write(tmp_path / "sensors.json", data)
    assert resolve_sensor_evidence(tmp_path, {}) == data


def test_tied_timestamp_prefers_failure(project):
    _, run, _ = project
    write(run / "sensors-full.json", sensor(run, passed=True))
    write(run / "sensors-all.json", sensor(run, tier="all"))
    assert resolve_sensor_evidence(run, {"required_sensors": ["test"]})["passed"] is False


@pytest.mark.parametrize("field,value", [("tier", []), ("run_dir", 42), ("passed", "true"), ("results", {})])
def test_invalid_evidence_shape_is_nonpassing(project, field, value):
    _, run, _ = project
    data = sensor(run, passed=True)
    data[field] = value
    write(run / "sensors-full.json", data)
    assert resolve_sensor_evidence(run, {"required_sensors": ["test"]})["passed"] is False


def test_empty_sensor_commands_do_not_require_full(tmp_path):
    data = {"tier": "smoke", "passed": True}
    write(tmp_path / "sensors.json", data)
    assert resolve_sensor_evidence(tmp_path, {"required_sensors": [" "]}) == data
