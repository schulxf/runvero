"""Sensor discovery, command parsing, and tier selection helpers."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Any

from harness_core.sensor_evidence import resolve_sensor_evidence
from harness_core.storage import read_json

SENSOR_TIERS = ["smoke", "affected", "full"]


def sensor_plan_digest(tier: str, commands: list[str], allow_shell: bool = False) -> str:
    plan = {
        "tier": tier,
        "commands": [str(command).strip() for command in commands],
        "allow_shell": bool(allow_shell),
    }
    encoded = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def make_sensor_review(sensor_tiers: dict[str, list[str]]) -> dict[str, Any]:
    from harness_core.clock import utc_now

    all_commands: list[str] = []
    for tier in SENSOR_TIERS:
        for command in sensor_tiers.get(tier, []):
            if command not in all_commands:
                all_commands.append(command)
    tier_digests = {
        tier: sensor_plan_digest(tier, sensor_tiers.get(tier, [])) for tier in SENSOR_TIERS
    }
    tier_digests["all"] = sensor_plan_digest("all", all_commands)
    configuration = json.dumps(
        {tier: sensor_tiers.get(tier, []) for tier in SENSOR_TIERS},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "digest": hashlib.sha256(configuration.encode()).hexdigest(),
        "tier_digests": tier_digests,
        "reviewed_at": utc_now(),
    }


def detect_default_sensors(root: Path) -> list[str]:
    sensors: list[str] = []
    package_json = root / "package.json"
    if package_json.exists():
        try:
            package = read_json(package_json, {})
            scripts = package.get("scripts", {})
            for script_name in ["lint", "typecheck", "test", "build"]:
                if script_name in scripts:
                    if script_name == "test":
                        sensors.append("npm test")
                    else:
                        sensors.append(f"npm run {script_name}")
        except Exception:
            pass

    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
        sensors.append("python -m pytest")

    return sensors


def split_sensor_command(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def resolve_sensor_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    executable = shutil.which(argv[0])
    if not executable:
        return argv
    return [executable, *argv[1:]]


def make_sensor_result(
    command: str,
    argv: list[str],
    resolved_argv: list[str],
    shell: bool,
    exit_code: int,
    duration_ms: int,
    stdout: str = "",
    stderr: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": command,
        "argv": argv,
        "resolved_argv": resolved_argv,
        "shell": shell,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout": stdout,
        "stderr": stderr,
    }
    payload.update(extra)
    return payload


def normalize_sensor_tiers(contract: dict[str, Any]) -> dict[str, list[str]]:
    configured = contract.get("sensor_tiers")
    tiers = {tier: [] for tier in SENSOR_TIERS}
    if isinstance(configured, dict):
        for tier in SENSOR_TIERS:
            values = configured.get(tier, [])
            if isinstance(values, list):
                tiers[tier] = [str(item) for item in values if str(item).strip()]

    legacy = [str(item) for item in contract.get("required_sensors", []) if str(item).strip()]
    if legacy:
        for command in legacy:
            if command not in tiers["full"]:
                tiers["full"].append(command)
    return tiers


def sensors_for_tier(contract: dict[str, Any], tier: str) -> list[str]:
    tiers = normalize_sensor_tiers(contract)
    if tier == "all":
        commands: list[str] = []
        for name in SENSOR_TIERS:
            for command in tiers[name]:
                if command not in commands:
                    commands.append(command)
        return commands
    if tier not in tiers:
        raise SystemExit(f"Tier de sensor invalido: {tier}")
    return tiers[tier]


def fastest_available_sensor_tier(contract: dict[str, Any]) -> str:
    tiers = normalize_sensor_tiers(contract)
    for tier in SENSOR_TIERS:
        if tiers[tier]:
            return tier
    return "full"


def final_sensor_payload(run_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    return resolve_sensor_evidence(run_dir, contract)
