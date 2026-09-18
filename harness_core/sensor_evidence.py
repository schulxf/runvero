"""One chronological sensor-evidence resolver, shared by gates and observers.

Never search backwards for a passing result. A newer failed or unreadable
attempt must not be replaced by an older success. This module does not approve
work: the existing review, plan-digest and source-surface gates still apply.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_EVIDENCE_BYTES = 2_000_000


def read_object(path: Path) -> dict[str, Any]:
    """Bounded JSON-object reader; reject symlinks and non-object documents."""
    if path.is_symlink():
        raise ValueError("symlink evidence is not supported")
    with path.open("rb") as handle:
        data = handle.read(MAX_EVIDENCE_BYTES + 1)
    if len(data) > MAX_EVIDENCE_BYTES:
        raise ValueError("evidence is too large")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("expected a JSON object")
    return result


def needs_full_sensors(contract: dict[str, Any]) -> bool:
    tiers = contract.get("sensor_tiers") or {}
    legacy = contract.get("required_sensors") or []
    full = tiers.get("full", []) if isinstance(tiers, dict) else []
    return any(str(item).strip() for values in (legacy, full) if isinstance(values, list) for item in values)


def _created_at(payload: dict[str, Any], path: Path) -> float:
    value = payload.get("created_at")
    if isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if date.tzinfo is not None:
                return date.astimezone(timezone.utc).timestamp()
        except ValueError:
            pass
    return path.lstat().st_mtime


def resolve_sensor_evidence(run_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    """Return the newest eligible attempt, never the most convenient success.

    Typed files are authoritative. sensors.json is a compatibility mirror used
    only when no eligible typed file exists. Legacy fixtures without identity
    fields remain readable; identity fields, when present, must match the run.
    """
    tiers = ("full", "all") if needs_full_sensors(contract) else ("full", "all", "affected", "smoke")
    paths = [run_dir / f"sensors-{tier}.json" for tier in tiers]
    paths = [path for path in paths if path.exists() or path.is_symlink()]
    if not paths:
        legacy = run_dir / "sensors.json"
        if not legacy.exists() and not legacy.is_symlink():
            return {}
        paths = [legacy]
    candidates = []
    for path in paths:
        try:
            payload = read_object(path)
            stamp = _created_at(payload, path)
        except (OSError, ValueError):
            payload = {"passed": False, "results": [], "evidence_error": "unreadable_sensor_evidence"}
            stamp = path.lstat().st_mtime
        # On equal timestamps a failure wins. Otherwise keep stable tier order.
        candidates.append((stamp, payload.get("passed") is not True, -len(candidates), payload))
    payload = max(candidates, key=lambda item: item[:3])[3]
    if payload.get("evidence_error"):
        return payload
    if "tier" in payload and not isinstance(payload["tier"], str):
        return {"passed": False, "results": [], "evidence_error": "invalid_tier"}
    if "passed" in payload and not isinstance(payload["passed"], bool):
        return {"passed": False, "results": [], "evidence_error": "invalid_status"}
    if "results" in payload and not isinstance(payload["results"], list):
        return {"passed": False, "results": [], "evidence_error": "invalid_results"}
    if needs_full_sensors(contract) and payload.get("tier") not in {"full", "all"}:
        return {}
    if payload.get("task_id") and payload["task_id"] != run_dir.parent.name:
        return {"passed": False, "results": [], "evidence_error": "wrong_task"}
    if payload.get("run_dir") and (not isinstance(payload["run_dir"], str) or Path(payload["run_dir"]).resolve() != run_dir.resolve()):
        return {"passed": False, "results": [], "evidence_error": "wrong_run"}
    return payload


def refresh_sensor_mirror(root: Path, run_dir: Path) -> None:
    """Refresh the compatibility mirror after a completed sensor invocation.

    Older dashboard/report/brief readers consume sensors.json. Resolve their
    mirror with the same function as final_sensor_payload so they cannot see an
    old full result while the approval gate sees a newer all result (or vice versa).
    Preliminary quick evidence remains visible until final sensors exist; the
    final resolver still refuses it when full sensors are required. Evidence
    without a contract is left alone.
    """
    import os
    import tempfile

    root, run_dir = root.resolve(), run_dir.absolute()
    contract_path = root / ".harness/contracts" / f"{run_dir.parent.name}.json"
    if not contract_path.exists():
        return
    if run_dir.parent.parent != root / ".harness/runs":
        raise ValueError("invalid run location")
    for target in (contract_path, run_dir / "sensors.json"):
        current = root
        for part in target.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("symlink state is not supported")
    contract = read_object(contract_path)
    payload = resolve_sensor_evidence(run_dir, contract)
    if not payload:
        return
    descriptor, temporary = tempfile.mkstemp(dir=run_dir, prefix=".sensors-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, run_dir / "sensors.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
