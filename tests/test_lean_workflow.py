"""Lean policy units and end-to-end runs through the real legacy CLI, without LLM calls."""
from __future__ import annotations

import json
import subprocess

import pytest

from harness_core import lean
from harness_core.jev_trigger import should_observe


def approved_review(*, role="reviewer", reviewer="review-session"):
    verification = {
        "task_id": "TASK-001", "run_id": "run-test", "source_digest": "source",
        "contract_digest": "contract", "verification_id": "verification",
        "language_required": False,
    }
    contract = {"acceptance_criteria": ["Expected behavior"]}
    review = {
        **{k: v for k, v in verification.items() if k != "language_required"},
        "role": role, "reviewer": reviewer, "decision": "pass", "risk": "standard",
        "notes": "Independently inspected the change and test outputs.",
        "criteria": [{"criterion": "Expected behavior", "status": "pass", "evidence": "test_app.py"}],
        "findings": [], "architecture": {"status": "pass", "evidence": "AGENTS.md and app.py"},
        "ptbr": {"status": "not_applicable", "evidence": "No user-facing text changed."},
    }
    return review, verification, contract


def test_combined_independent_review_is_accepted():
    review, verification, contract = approved_review()
    lean.validate_review(review, verification, contract, "builder", "reviewer")


@pytest.mark.parametrize("field,value", [
    ("task_id", "other"), ("run_id", "other"), ("source_digest", "old"),
    ("contract_digest", "old"), ("verification_id", "old"),
    ("reviewer", "builder"), ("reviewer", " BUILDER "), ("reviewer", ""),
    ("reviewer", 5), ("decision", "needs-work"), ("decision", "fail"),
    ("risk", "low"), ("role", "builder"), ("notes", ""), ("notes", 123),
    ("criteria", []), ("criteria", "pass"),
    ("findings", [{"severity": "P0", "message": "Problem"}]),
    ("findings", [{"severity": "P1", "message": "Problem"}]),
    ("findings", [{"severity": "low", "message": "Problem"}]),
    ("findings", [{"severity": "P2", "message": 123}]),
    ("findings", None), ("architecture", {"status": "pass", "evidence": ""}),
    ("architecture", {"status": "not_checked", "evidence": "Unknown"}),
    ("architecture", "pass"), ("ptbr", {"status": "not_applicable", "evidence": ""}),
    ("ptbr", {"status": "pass", "evidence": 123}), ("ptbr", "pass"),
])
def test_invalid_review_fails_closed(field, value):
    review, verification, contract = approved_review()
    review[field] = value
    with pytest.raises(ValueError):
        lean.validate_review(review, verification, contract, "builder", "reviewer")


@pytest.mark.parametrize("field,value", [("criterion", "Another criterion"), ("status", "not_checked"), ("evidence", ""), ("evidence", 12)])
def test_each_criterion_requires_matching_evidence(field, value):
    review, verification, contract = approved_review()
    review["criteria"][0][field] = value
    with pytest.raises(ValueError):
        lean.validate_review(review, verification, contract, "builder", "reviewer")


def test_language_not_applicable_is_not_a_fake_pass():
    review, verification, contract = approved_review()
    verification["language_required"] = True
    with pytest.raises(ValueError, match="PT-BR"):
        lean.validate_review(review, verification, contract, "builder", "reviewer")
    review["ptbr"] = {"status": "pass", "evidence": "Text reviewed in README.md."}
    lean.validate_review(review, verification, contract, "builder", "reviewer")


@pytest.mark.parametrize("path", [
    "apps/api/auth/service.py", "src/auth_service.py", "src/useBilling.ts",
    "data/migrations/001.sql", "infra/main.tf", ".github/workflows/ci.yml",
    "package.json", "pnpm-lock.yaml", "AGENTS.md", "docs/adr/0001.md",
    "src/permissions.ts", "apps/middleware.ts", "src/tenant_handler.py",
])
def test_sensitive_path_escalation(path):
    assert lean.sensitive_paths([path], []) == [path]


def test_extra_critical_paths_are_additive():
    assert lean.sensitive_paths(["src/calculation.py", "auth/policy.py"], ["src/calculation.py"]) == ["src/calculation.py", "auth/policy.py"]
    assert lean.sensitive_paths(["src/calculation.py"], []) == []


@pytest.mark.parametrize("path,required", [("README.md", True), ("ui/view.tsx", True), ("locales/pt.json", True), ("service.py", False), ("lib/calc.ts", False)])
def test_language_applicability(path, required):
    assert lean.language_required([path]) is required


@pytest.mark.parametrize("trigger,passed,expected", [
    (None, False, True), (None, True, False), ("failures", False, True),
    ("failures", True, False), ("failures", None, False), ("failures", 0, False),
    ("always", True, True), ("always", False, True), ("always", 0, False),
    ("manual", False, False), ("typo", False, False), (False, False, False),
])
def test_jev_automatic_trigger(trigger, passed, expected):
    settings = {"enabled": True, "mode": "shadow", "allow_remote_state": True}
    if trigger is not None:
        settings["automatic_trigger"] = trigger
    assert should_observe({"jev_observer": settings}, {"passed": passed}) is expected


@pytest.mark.parametrize("settings", [{}, None, "enabled", {"enabled": "true", "allow_remote_state": True}, {"enabled": True, "allow_remote_state": "true"}, {"enabled": True, "allow_remote_state": True, "mode": "autonomous"}])
def test_jev_requires_existing_explicit_consent(settings):
    assert should_observe({"jev_observer": settings}, {"passed": False}) is False


def test_bounded_review_input(tmp_path):
    path = tmp_path / "review.json"
    path.write_text("[]")
    with pytest.raises(ValueError):
        lean.read_object(path)
    path.write_text(" " * (lean.MAX_REVIEW_BYTES + 1))
    with pytest.raises(ValueError, match="limite"):
        lean.read_object(path)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_HUB_CONTROL_REPO", "disabled")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    repo = tmp_path / "project"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "feature/lean-test")
    _git(repo, "config", "user.name", "Tests")
    _git(repo, "config", "user.email", "tests@example.com")
    (repo / "AGENTS.md").write_text("Keep architecture checks. Do not create forbidden.py.\n")
    (repo / "app.py").write_text("value = 1\n")
    (repo / "checks.py").write_text("import runpy\nassert runpy.run_path('app.py')['value'] == 2\n")
    (repo / "architecture_check.py").write_text("from pathlib import Path\nassert not Path('forbidden.py').exists()\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo


def _run(repo, *args):
    return lean.main(["--repo", str(repo), *args])


def _prepare(repo, *extra):
    assert _run(
        repo, "prepare", "Update value", "--builder", "builder",
        "--criteria", "value is 2", "--sensor", "python checks.py",
        "--quick-sensor", "python checks.py", "--architecture-sensor", "python architecture_check.py",
        "--reviewed-sensors", *extra,
    ) == 0
    return lean._legacy().latest_run_dir(repo, "TASK-001")


def _verify(repo):
    (repo / "app.py").write_text("value = 2\n")
    assert _run(repo, "verify", "TASK-001") == 0


def _review(run_dir, *, name="reviewer", role="reviewer", risk=None):
    review = json.loads((run_dir / "lean/review-request.json").read_text())
    review.update(reviewer=name, role=role, decision="pass", notes="Independently reviewed criteria and checks.")
    if risk:
        review["risk"] = risk
    for item in review["criteria"]:
        item.update(status="pass", evidence="checks.py output and app.py inspected.")
    review["architecture"] = {"status": "pass", "evidence": "AGENTS.md and architecture_check.py inspected."}
    review["ptbr"] = {"status": "not_applicable", "evidence": "No user-facing text changed."}
    return review


def _save_review(run_dir, review, filename="review-input.json"):
    path = run_dir / "lean" / filename
    path.write_text(json.dumps(review), encoding="utf-8")
    return str(path)


def test_flow_standard_finishes_with_one_real_review_and_explicit_na(project):
    run_dir = _prepare(project)
    config_before = (project / ".harness/config.json").read_bytes()
    (project / "app.py").write_text("value = 2\n")
    assert _run(project, "check", "TASK-001") == 0
    assert not (run_dir / "lean/review-handoff.md").exists()
    assert not (run_dir / "parallel-dispatch.md").exists()
    assert _run(project, "verify", "TASK-001") == 0
    assert not (run_dir / "evaluation.json").exists()
    review_path = _save_review(run_dir, _review(run_dir))
    assert _run(project, "finish", "TASK-001", "--review", review_path) == 0
    assert lean._legacy().find_task(project, "TASK-001")["status"] == "passed"
    assert not (run_dir / "ptbr-review.json").exists()
    assert json.loads((run_dir / "lean/applicability.json").read_text())["ptbr"]["status"] == "not_applicable"
    assert (project / ".harness/config.json").read_bytes() == config_before
    assert (project / ".harness/reports/TASK-001.md").exists()
    # Existing PR gate understands run-local applicability; it does not need fake pass files.
    lean._legacy().require_github_pr_create_gate(project, "TASK-001", lean._legacy().load_config(project))


def test_flow_failed_architecture_sensor_blocks_review(project):
    run_dir = _prepare(project)
    (project / "app.py").write_text("value = 2\n")
    (project / "forbidden.py").write_text("value = 'not allowed'\n")
    assert _run(project, "verify", "TASK-001") != 0
    assert not (run_dir / "lean/review-request.json").exists()
    assert not (run_dir / "evaluation.json").exists()


@pytest.mark.parametrize("change", ["source", "contract", "config", "sensors"])
def test_flow_stale_evidence_cannot_approve(project, change):
    run_dir = _prepare(project)
    _verify(project)
    review_path = _save_review(run_dir, _review(run_dir))
    if change == "source":
        (project / "app.py").write_text("value = 3\n")
    elif change == "contract":
        path = project / ".harness/contracts/TASK-001.json"
        value = json.loads(path.read_text())
        value["acceptance_criteria"] = ["Something different"]
        path.write_text(json.dumps(value))
    elif change == "config":
        path = project / ".harness/config.json"
        value = json.loads(path.read_text())
        value["project_name"] = "changed"
        path.write_text(json.dumps(value))
    else:
        path = run_dir / "sensors-full.json"
        value = json.loads(path.read_text())
        value["passed"] = False
        path.write_text(json.dumps(value))
    assert _run(project, "finish", "TASK-001", "--review", review_path) != 0
    assert not (run_dir / "evaluation.json").exists()


def test_flow_sensitive_change_requires_second_independent_evaluator(project):
    run_dir = _prepare(project)
    (project / "migration.sql").write_text("-- migration example\n")
    _verify(project)
    review_path = _save_review(run_dir, _review(run_dir))
    assert _run(project, "finish", "TASK-001", "--review", review_path) != 0
    same = _review(run_dir, role="evaluator")
    evaluator_path = _save_review(run_dir, same, "eval-input.json")
    assert _run(project, "finish", "TASK-001", "--review", review_path, "--evaluation", evaluator_path) != 0
    different = _review(run_dir, name="separate-evaluator", role="evaluator")
    evaluator_path = _save_review(run_dir, different, "eval-input.json")
    assert _run(project, "finish", "TASK-001", "--review", review_path, "--evaluation", evaluator_path) == 0


def test_flow_reviewer_can_escalate_even_when_paths_look_normal(project):
    run_dir = _prepare(project)
    _verify(project)
    path = _save_review(run_dir, _review(run_dir, risk="critical"))
    assert _run(project, "finish", "TASK-001", "--review", path) != 0


def test_flow_text_changes_require_actual_language_review(project):
    run_dir = _prepare(project)
    (project / "README.md").write_text("# Texto alterado\n")
    _verify(project)
    review = _review(run_dir)
    path = _save_review(run_dir, review)
    assert _run(project, "finish", "TASK-001", "--review", path) != 0
    review["ptbr"] = {"status": "pass", "evidence": "Ortografia e clareza conferidas em README.md."}
    path = _save_review(run_dir, review)
    assert _run(project, "finish", "TASK-001", "--review", path) == 0
    assert json.loads((run_dir / "ptbr-review.json").read_text())["status"] == "pass"


def test_flow_time_budget_advisory_for_standard_only(project):
    run_dir = _prepare(project)
    _verify(project)
    path = run_dir / "run.json"
    run = json.loads(path.read_text())
    run["created_at"] = "2000-01-01T00:00:00Z"
    path.write_text(json.dumps(run))
    review_path = _save_review(run_dir, _review(run_dir))
    assert _run(project, "finish", "TASK-001", "--review", review_path) == 0


def test_flow_critical_budget_failure_restores_original_metadata(project):
    run_dir = _prepare(project, "--risk", "critical")
    _verify(project)
    path = run_dir / "run.json"
    original = json.loads(path.read_text())
    original["created_at"] = "2000-01-01T00:00:00Z"
    path.write_text(json.dumps(original))
    review_path = _save_review(run_dir, _review(run_dir))
    evaluator_path = _save_review(run_dir, _review(run_dir, name="evaluator", role="evaluator"), "eval-input.json")
    assert _run(project, "finish", "TASK-001", "--review", review_path, "--evaluation", evaluator_path) != 0
    assert json.loads(path.read_text()) == original
    assert not (run_dir / "evaluation.json").exists()


def test_flow_no_rules_or_unreviewed_commands_cannot_start(project):
    assert _run(project, "prepare", "Task", "--builder", "builder", "--criteria", "works", "--sensor", "python checks.py") != 0
    assert not (project / ".harness/config.json").exists()
    (project / "AGENTS.md").unlink()
    _git(project, "add", ".")
    _git(project, "commit", "-m", "fixture without rules")
    assert _run(project, "prepare", "Task", "--builder", "builder", "--criteria", "works", "--sensor", "python checks.py", "--reviewed-sensors") != 0
    assert not (project / ".harness/runs/TASK-001").exists()


def test_flow_main_branch_cannot_be_modified(project):
    _git(project, "checkout", "-b", "main")
    assert _run(project, "prepare", "Task", "--builder", "builder", "--criteria", "works", "--sensor", "python checks.py", "--reviewed-sensors") != 0
    assert not (project / ".harness").exists()


def test_flow_jev_is_called_for_failures_not_successes(project, monkeypatch):
    from harness_core import event_pipeline

    run_dir = _prepare(project)
    config_path = project / ".harness/config.json"
    config = json.loads(config_path.read_text())
    config["jev_observer"] = {"enabled": True, "allow_remote_state": True, "mode": "shadow"}
    config_path.write_text(json.dumps(config))
    calls = []

    def observer(root, folder):
        calls.append((root, folder))
        return {"status": "observed", "recommendation": "Hipótese para investigação.", "applied": False}

    monkeypatch.setattr(event_pipeline, "observe", observer)
    assert _run(project, "check", "TASK-001") != 0
    assert len(calls) == 1
    assert not (run_dir / "evaluation.json").exists()
    (project / "app.py").write_text("value = 2\n")
    assert _run(project, "check", "TASK-001") == 0
    assert len(calls) == 1


def test_flow_unavailable_jev_never_fails_successful_sensors(project, monkeypatch):
    from harness_core import event_pipeline

    _prepare(project)
    config_path = project / ".harness/config.json"
    config = json.loads(config_path.read_text())
    config["jev_observer"] = {"enabled": True, "allow_remote_state": True, "automatic_trigger": "always"}
    config_path.write_text(json.dumps(config))

    def unavailable(*args):
        raise RuntimeError("sensitive SDK error must not escape")

    monkeypatch.setattr(event_pipeline, "observe", unavailable)
    (project / "app.py").write_text("value = 2\n")
    assert _run(project, "check", "TASK-001") == 0
