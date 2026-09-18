from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .agent_registry import load_agent_registry, upsert_agent
from .clock import utc_now
from .config import config_bool, telegram_config
from .context_preflight import load_config
from .events import append_harness_event
from .hub_agents import hub_agent_name_for_role, sector_for_event
from .jev_observer import observe
from .paths import config_path, relative_to_root, telegram_root, to_posix
from .run_state import find_unevaluated_runs
from .sensor_evidence import refresh_sensor_mirror
from .storage import append_jsonl
from .task_store import find_task
from .telegram import telegram_send_message


def sync_agent_from_event(root: Path, event: dict[str, Any]) -> None:
    event_type = str(event.get("type") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    task_id = str(event.get("task_id") or payload.get("task_id") or "")
    if not task_id:
        return
    task_title = ""
    try:
        task_title = str(find_task(root, task_id).get("title") or "")
    except SystemExit:
        pass
    role = {
        "run_started": "builder",
        "sensors_completed": "builder",
        "evaluation_brief_created": "reviewer",
        "evaluation_recorded": "reviewer",
        "fix_brief_created": "builder",
        "report_created": "reporter",
    }.get(event_type, "operator")
    state = {
        "evaluation_recorded": "idle",
        "report_created": "idle",
    }.get(event_type, "working")
    phase = {
        "run_started": "build",
        "sensors_completed": "review" if payload.get("passed") else "build",
        "evaluation_brief_created": "review",
        "evaluation_recorded": "report" if payload.get("status") == "pass" else "build",
        "fix_brief_created": "build",
        "report_created": "report",
    }.get(event_type, role)
    speech = payload.get("summary") or {
        "run_started": f"Comecei {task_id}.",
        "sensors_completed": f"Conferencias de {task_id} {'passaram' if payload.get('passed') else 'falharam'}.",
        "evaluation_brief_created": f"Revisao pronta para {task_id}.",
        "evaluation_recorded": f"Decisao de {task_id}: {payload.get('status')}.",
        "fix_brief_created": f"Preparando correcao de {task_id}.",
        "report_created": f"Relatorio de {task_id} fechado.",
    }.get(event_type, f"Atualizei {task_id}.")
    agent_id = str(event.get("agent_id") or f"{role}-{task_id}").lower()
    previous = next(
        (
            item
            for item in load_agent_registry(root).get("agents", [])
            if isinstance(item, dict) and item.get("id") == agent_id
        ),
        {},
    )
    sector = sector_for_event(event_type, payload)
    agent = upsert_agent(
        root,
        agent_id,
        name=hub_agent_name_for_role(role),
        role=role,
        state=state,
        task_id=task_id,
        task_title=task_title,
        phase=phase,
        speech=str(speech),
        run_dir=str(event.get("run_dir") or ""),
        event_id=str(event.get("id") or ""),
        sector=sector,
        spawned_by="event",
    )
    if sector and sector != str(previous.get("sector") or ""):
        append_harness_event(
            root,
            "agent_sector_changed",
            {
                "agent_id": agent_id,
                "sector": agent.get("sector") or sector,
                "summary": f"{agent.get('name') or agent_id} foi para {agent.get('sector') or sector}.",
            },
            task_id=task_id,
            agent_id=agent_id,
            source="hub",
        )


def telegram_event_message(
    root: Path,
    run_dir: Path,
    event_type: str,
    payload: dict[str, Any],
) -> str:
    task_id = str(payload.get("task_id") or run_dir.parent.name)
    project = load_config(root).get("project_name") if config_path(root).exists() else root.name
    if event_type == "run_started":
        return f"Harness: {project}\n{task_id} comecou.\nRun: {run_dir.name}"
    if event_type == "sensors_completed":
        status = "passaram" if payload.get("passed") else "falharam"
        return f"Harness: {project}\nConferencias de {task_id} {status}."
    if event_type == "evaluation_brief_created":
        return f"Harness: {project}\n{task_id} esta pronto para avaliacao e revisao."
    if event_type == "evaluation_recorded":
        return f"Harness: {project}\nDecisao registrada para {task_id}: {payload.get('status')}."
    if event_type == "fix_brief_created":
        count = len(payload.get("blocking_findings") or [])
        return f"Harness: {project}\nFix brief criado para {task_id} com {count} bloqueador(es)."
    if event_type == "report_created":
        summary = payload.get("plain_summary")
        message = f"Harness: {project}\nRelatorio final criado para {task_id}."
        if summary:
            message += f"\n\n{summary}"
        return message
    return f"Harness: {project}\nEvento {event_type} em {task_id}."


def append_and_maybe_notify_event(
    root: Path,
    run_dir: Path,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    if event_type == "sensors_completed":
        refresh_sensor_mirror(root, run_dir)
    event = append_harness_event(root, event_type, payload, run_dir=run_dir)
    sync_agent_from_event(root, event)
    if event_type == "sensors_completed":
        observation = observe(root, run_dir)
        if observation.get("status") == "observed":
            print(f"Jev (somente observação): {observation['recommendation']}", file=sys.stderr)
    try:
        config = load_config(root)
        tconfig = telegram_config(config)
        if not config_bool(tconfig.get("enabled"), False):
            return
        if event_type not in set(str(item) for item in tconfig.get("notify_events", [])):
            return
        telegram_send_message(config, telegram_event_message(root, run_dir, event_type, payload))
    except Exception as exc:
        append_jsonl(
            telegram_root(root) / "notify-errors.jsonl",
            {"ts": utc_now(), "event_type": event_type, "error": str(exc)},
        )


def maybe_warn_unevaluated_runs(root: Path, config: dict[str, Any], task_id: str | None = None) -> None:
    policy = config.get("policy", {})
    if not policy.get("warn_on_unevaluated_runs", False):
        return

    unevaluated = find_unevaluated_runs(root, task_id)
    if not unevaluated:
        return

    scope = f" para {task_id}" if task_id else ""
    print(
        f"Aviso: {len(unevaluated)} run(s){scope} ainda nao tem avaliacao registrada.",
        file=sys.stderr,
    )
    for item in unevaluated[:10]:
        sensors = "com sensores" if item["has_sensors"] else "sem sensores"
        run_path = to_posix(relative_to_root(root, Path(item["run_dir"])))
        print(
            f"- {item['task_id']} {item['run_id']} ({sensors}): {run_path}",
            file=sys.stderr,
        )
    if len(unevaluated) > 10:
        print(f"- ... mais {len(unevaluated) - 10} run(s)", file=sys.stderr)
