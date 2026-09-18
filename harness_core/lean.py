"""A small prepare/check/verify/finish workflow over the existing Harness gates.

No model orchestration, autonomous approval, new storage engine or runtime deps.
The legacy CLI remains unchanged. Reviews are operator-supplied attestations,
not authenticated identities; local filesystem access remains a trust boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

VERSION = "lean-v1"
MAX_REVIEW_BYTES = 256_000
# Conservative escalation hints, not a semantic security classifier.
CRITICAL_PARTS = {
    "auth", "authorization", "authentication", "permissions", "security",
    "billing", "payments", "migrations", "migration", "infra", "infrastructure",
    "terraform", "deploy", "deployment", "workflows", "tenancy", "tenant", "tenants",
    "rls", "rbac", "middleware", "credentials", "secrets",
}
CRITICAL_NAMES = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "pyproject.toml", "requirements.txt", "requirements-dev.txt", "poetry.lock",
    "uv.lock", "cargo.toml", "cargo.lock", "go.mod", "go.sum", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "agents.md", "claude.md",
    "codeowners",
}
TEXT_SUFFIXES = {".md", ".mdx", ".txt", ".html", ".jsx", ".tsx", ".vue", ".po", ".pot"}


@lru_cache(maxsize=1)
def _legacy():
    path = Path(__file__).resolve().parent.parent / "bin" / "harness.py"
    spec = importlib.util.spec_from_file_location("_runvero_legacy", path)
    if spec is None or spec.loader is None:
        raise ValueError("CLI legado indisponível; execute a partir de um checkout completo.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"Arquivo de evidência não pode ser symlink: {path.name}")
    with path.open("rb") as handle:
        raw = handle.read(MAX_REVIEW_BYTES + 1)
    if len(raw) > MAX_REVIEW_BYTES:
        raise ValueError("Arquivo de evidência excede o limite.")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Evidência deve ser um objeto JSON.")
    return value


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, timeout=30, check=False,
    )
    if result.returncode:
        raise ValueError("Não foi possível conferir o estado Git; nenhuma aprovação foi registrada.")
    return result.stdout


def changed_paths(root: Path, base: str) -> list[str]:
    paths = git(root, "diff", "--name-only", "--no-renames", "-z", base, "--").split(b"\0")
    paths += git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    return sorted({
        p.decode("utf-8", errors="surrogateescape") for p in paths
        if p and not p.startswith(b".harness/")
    })


def sensitive_paths(paths: list[str], extra: list[str]) -> list[str]:
    result = []
    for raw in paths:
        path = Path(raw.lower())
        parts = set(path.parts)
        stem = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", Path(raw).stem).lower()
        name_parts = set(stem.replace("-", "_").replace(".", "_").split("_"))
        if (
            parts & CRITICAL_PARTS or name_parts & CRITICAL_PARTS
            or path.name in CRITICAL_NAMES or path.suffix in {".sql", ".tf", ".tfvars"}
            or "adr" in parts or raw.lower().startswith(".github/")
            or any(Path(raw).match(pattern) for pattern in extra)
        ):
            result.append(raw)
    return result


def language_required(paths: list[str]) -> bool:
    return any(
        Path(p).suffix.lower() in TEXT_SUFFIXES
        or {"locales", "translations", "i18n"} & set(Path(p.lower()).parts)
        for p in paths
    )


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(s, str) or not s.strip() for s in value):
        raise ValueError(f"{name} deve ser uma lista de textos não vazios.")
    return list(dict.fromkeys(value))


def _call(cli, root: Path, *args: str) -> None:
    result = cli.main(["--repo", str(root), *args])
    if result not in (None, 0):
        raise ValueError(f"Comando {args[0]} falhou; nenhuma etapa foi dispensada.")


def _load(cli, root: Path, task_id: str):
    cli.require_safe_branch(root, argparse.Namespace(allow_main=False), "runvero")
    cli.find_task(root, task_id)
    run_dir = cli.latest_run_dir(root, task_id)
    meta = read_object(run_dir / "lean.json")
    if meta.get("version") != VERSION or meta.get("task_id") != task_id or meta.get("run_id") != run_dir.name:
        raise ValueError("Esta execução não foi preparada pelo fluxo enxuto.")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(meta.get("base_commit", ""))):
        raise ValueError("Base Git inválida.")
    if not isinstance(meta.get("original_budget"), dict):
        raise ValueError("Snapshot de orçamento inválido.")
    contract, config = cli.load_contract(root, task_id), cli.load_config(root)
    if not isinstance(config.get("lean", {}), dict):
        raise ValueError("Configuração lean inválida.")
    if meta.get("contract_digest") != digest(contract):
        raise ValueError("Contrato alterado após prepare; replaneje explicitamente pelo fluxo completo.")
    architecture = _strings(config.get("lean", {}).get("architecture_sensors", []), "architecture_sensors")
    if any(command not in cli.sensors_for_tier(contract, "full") for command in architecture):
        raise ValueError("Verificador arquitetural fora do contrato; replaneje os sensores explicitamente.")
    return run_dir, meta, contract, config


def _identity(cli, root: Path, run_dir: Path, meta: dict, contract: dict, config: dict) -> dict:
    return {
        "task_id": meta["task_id"], "run_id": run_dir.name,
        "source_digest": cli.source_surface_digest(root),
        "contract_digest": digest(contract), "config_digest": digest(config),
        "meta_digest": digest(meta),
    }


def _prepare(cli, root: Path, args: argparse.Namespace) -> None:
    base = git(root, "rev-parse", "HEAD").decode().strip()
    if changed_paths(root, base):
        raise ValueError("Prepare antes de implementar, em uma worktree limpa (fora de .harness/).")
    if not args.reviewed_sensors:
        raise ValueError("Revise os comandos e confirme com --reviewed-sensors.")
    if not (root / ".harness/config.json").exists():
        _call(cli, root, "init")
    cli.require_safe_branch(root, argparse.Namespace(allow_main=False), "runvero prepare")
    config = cli.load_config(root)
    options = config.get("lean", {})
    if not isinstance(options, dict):
        raise ValueError("Configuração lean inválida.")
    architecture = _strings(options.get("architecture_sensors", []), "architecture_sensors")
    architecture += args.architecture_sensor
    sensors = _strings(args.sensor + architecture, "sensores")
    criteria = _strings(args.criteria, "critérios")
    if not criteria or not sensors or not args.builder.strip():
        raise ValueError("Informe critérios, sensores finais e a identidade do implementador.")
    docs: dict[str, str] = {}
    for item in config.get("required_context", []):
        if isinstance(item, str):
            docs[item] = "context"
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            docs[item["path"]] = item.get("kind") or "context"
        else:
            raise ValueError("Contexto obrigatório inválido.")
    if (root / "AGENTS.md").is_file():
        docs.setdefault("AGENTS.md", "context")
    for path in args.required_doc:
        docs.setdefault(path, "architecture")
    if not docs:
        raise ValueError("Forneça AGENTS.md ou --required-doc com as regras da aplicação.")
    for raw, kind in docs.items():
        path = (root / raw).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Documento obrigatório inválido: {raw}")
        # Deterministic refresh; no agent has to recreate a context-ingestion ritual.
        _call(cli, root, "ingest", str(path), "--kind", kind)
    task = cli.create_task(root, args.title, args.body or args.title, "runvero prepare")
    task_id = task["task_id"]
    command = ["contract", task_id, "--reviewed-sensors"]
    for flag, values in (
        ("--criteria", criteria), ("--full-sensor", sensors),
        ("--smoke-sensor", args.quick_sensor), ("--required-doc", list(docs)),
        ("--out", args.out),
    ):
        for value in values:
            command += [flag, value]
    _call(cli, root, *command)
    _call(cli, root, "start", task_id)
    run_dir = cli.latest_run_dir(root, task_id)
    meta = {
        "version": VERSION, "task_id": task_id, "run_id": run_dir.name,
        "builder": args.builder.strip(), "risk": args.risk, "base_commit": base,
        "architecture_sensors": architecture, "required_docs": list(docs),
        "contract_digest": digest(cli.load_contract(root, task_id)),
        "original_budget": read_object(run_dir / "run.json")["budget"],
    }
    cli.write_json(run_dir / "lean.json", meta)
    brief = (
        f"# Implementação — {task_id}\n\n{args.body or args.title}\n\n"
        "## Critérios\n" + "\n".join(f"- {s}" for s in criteria)
        + "\n\n## Regras da aplicação\n"
        + "\n".join(f"- Leia `{p}` na origem; não altere regras para justificar o diff." for p in docs)
        + "\n\n## Execução\n"
        "Implemente diretamente, dentro do escopo, e teste durante o trabalho. "
        "Use `check` para feedback rápido, sem convocar revisores. "
        "Use `verify` quando houver uma mudança coerente para revisão independente. "
        "Não publique, não altere permissões e não execute operações destrutivas sem autorização. "
        "Pause para decisão quando precisar desviar da arquitetura ou ampliar o escopo. "
        "Checkpoints são úteis para interrupções e trabalho longo, não uma exigência por edição.\n\n"
        "## Fora de escopo\n" + "\n".join(f"- {s}" for s in args.out)
        + "\n\n## Verificações finais revisadas\n" + "\n".join(f"- `{s}`" for s in sensors)
        + "\n\nOs documentos orientam o agente; somente verificações e review podem detectar violações.\n"
    )
    cli.write_text(run_dir / "builder-brief.md", brief)
    print(f"Runvero: {task_id} preparado. Implemente; depois execute verify {task_id}.")


def _verify(cli, root: Path, args: argparse.Namespace) -> None:
    run_dir, meta, contract, config = _load(cli, root, args.task_id)
    before = _identity(cli, root, run_dir, meta, contract, config)
    _call(cli, root, "sensors", args.task_id, "--tier", "quick" if args.action == "check" else "full")
    if args.action == "check":
        tier = cli.fastest_available_sensor_tier(contract)
        if not cli.read_json(run_dir / f"sensors-{tier}.json", {}).get("passed"):
            raise ValueError("Sensores rápidos falharam. Corrija e tente novamente; JEV pode auxiliar.")
        return
    sensor = cli.final_sensor_payload(run_dir, contract)
    if not sensor.get("passed"):
        raise ValueError("Sensores finais falharam. Não há handoff nem aprovação.")
    _call(cli, root, "security", "scan", "--task-id", args.task_id, "--fail-on-findings")
    fresh_dir, fresh_meta, fresh_contract, fresh_config = _load(cli, root, args.task_id)
    after = _identity(cli, root, fresh_dir, fresh_meta, fresh_contract, fresh_config)
    if before != after:
        raise ValueError("Código, contrato ou configuração mudou durante as verificações; execute verify novamente.")
    paths = changed_paths(root, meta["base_commit"])
    extra = _strings(config.get("lean", {}).get("critical_paths", []), "critical_paths")
    sensitive = sensitive_paths(paths, extra)
    risk = "critical" if meta["risk"] == "critical" or sensitive else "standard"
    security = read_object(run_dir / "security-scan.json")
    verification = {
        **after, "risk": risk, "sensitive_paths": sensitive, "changed_paths": paths,
        "language_required": language_required(paths),
        "sensor_digest": digest(sensor), "security_digest": digest(security),
    }
    verification["verification_id"] = digest(verification)
    folder = run_dir / "lean"
    cli.write_json(folder / "verification.json", verification)
    template = {
        **{k: verification[k] for k in ("task_id", "run_id", "source_digest", "contract_digest", "verification_id")},
        "role": "reviewer", "reviewer": "", "decision": "needs-work", "risk": risk,
        "notes": "", "criteria": [
            {"criterion": c, "status": "not_checked", "evidence": ""}
            for c in contract["acceptance_criteria"]
        ],
        "findings": [], "architecture": {"status": "not_checked", "evidence": ""},
        "ptbr": {"status": "not_checked", "evidence": ""},
    }
    cli.write_json(folder / "review-request.json", template)
    handoff = (
        f"# Revisão independente — {args.task_id}\n\n"
        f"Repositório: `{root}`\nBase: `{meta['base_commit']}`\nRisco: `{risk}`\n\n"
        "Abra uma sessão nova, sem herdar as conclusões do implementador. "
        "Examine o contrato, as regras na origem, TODO o diff desde a base, arquivos novos, "
        "testes e resultados. Os caminhos sensíveis são dicas, não limites da revisão. "
        "Não edite código nem reduza testes. Verifique efeitos em autorização, persistência, "
        "integrações, compatibilidade e escopo. Eleve risk para critical quando houver dúvida relevante.\n\n"
        f"Contrato: `{root / '.harness/contracts' / (args.task_id + '.json')}`\n"
        f"Evidências: `{run_dir}`\n"
        "Regras: " + ", ".join(f"`{p}`" for p in meta["required_docs"])
        + "\n\nCopie `review-request.json` para `review.json`; preencha identidade, decisão, "
        "evidência por critério, arquitetura e findings com severity P0/P1/P2/P3. "
        "PT-BR pode ser not_applicable somente com justificativa quando não houve texto relevante. "
        "Campos vazios/not_checked não aprovam. Não invente comprovação de testes ou revisão.\n\n"
        "Se o risco for critical, obtenha também `evaluation.json` de OUTRA sessão independente, "
        "com o mesmo formato e role=evaluator. O implementador nunca é um dos aprovadores. "
        "Nomes declarados não são uma prova técnica de isolamento: o operador deve assegurar as sessões.\n"
    )
    cli.write_text(folder / "review-handoff.md", handoff)
    print(f"Revisão pronta: {folder / 'review-handoff.md'} ({risk}). Nenhuma tarefa foi aprovada.")


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_review(review: dict, verification: dict, contract: dict, builder: str, role: str) -> None:
    for key in ("task_id", "run_id", "source_digest", "contract_digest", "verification_id"):
        if review.get(key) != verification[key]:
            raise ValueError(f"Parecer pertence a outro estado: {key}.")
    author = review.get("reviewer")
    if not isinstance(author, str) or not author.strip() or author.strip().casefold() == builder.casefold():
        raise ValueError("Revisão exige identidade independente do implementador.")
    if review.get("role") != role or review.get("risk") not in {"standard", "critical"}:
        raise ValueError("Papel ou risco do parecer inválido.")
    if review.get("decision") != "pass" or not _has_text(review.get("notes")):
        raise ValueError("Parecer não aprova a entrega ou não contém justificativa.")
    entries = review.get("criteria")
    expected = contract["acceptance_criteria"]
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ValueError("Parecer não cobre todos os critérios contratados.")
    for criterion, item in zip(expected, entries, strict=True):
        if not isinstance(item, dict) or item.get("criterion") != criterion or item.get("status") != "pass" or not _has_text(item.get("evidence")):
            raise ValueError("Critério sem evidência de aprovação.")
    architecture = review.get("architecture", {})
    if not isinstance(architecture, dict) or architecture.get("status") != "pass" or not _has_text(architecture.get("evidence")):
        raise ValueError("Falta revisão das regras de arquitetura aplicáveis.")
    findings = review.get("findings")
    if not isinstance(findings, list):
        raise ValueError("Lista de achados inválida.")
    for item in findings:
        if not isinstance(item, dict) or item.get("severity") not in {"P0", "P1", "P2", "P3"} or not _has_text(item.get("message")):
            raise ValueError("Achado inválido.")
        if item["severity"] in {"P0", "P1"}:
            raise ValueError("Há achados P0/P1; corrija antes de aprovar.")
    language = review.get("ptbr", {})
    if not isinstance(language, dict) or language.get("status") not in {"pass", "not_applicable"} or not _has_text(language.get("evidence")):
        raise ValueError("Revisão PT-BR exige evidência ou justificativa de não aplicabilidade.")
    if verification["language_required"] and language["status"] != "pass":
        raise ValueError("Arquivos com possível texto foram alterados; registre a revisão PT-BR real.")


def _finish(cli, root: Path, args: argparse.Namespace) -> None:
    run_dir, meta, contract, config = _load(cli, root, args.task_id)
    folder = run_dir / "lean"
    verification = read_object(folder / "verification.json")
    if verification.get("verification_id") != digest({k: v for k, v in verification.items() if k != "verification_id"}):
        raise ValueError("Snapshot de verificação inconsistente.")
    for key, value in _identity(cli, root, run_dir, meta, contract, config).items():
        if verification.get(key) != value:
            raise ValueError("Verificação desatualizada; execute verify e obtenha novo parecer.")
    sensor = cli.final_sensor_payload(run_dir, contract)
    security = read_object(run_dir / "security-scan.json")
    if digest(sensor) != verification["sensor_digest"] or digest(security) != verification["security_digest"]:
        raise ValueError("Evidências mudaram depois da verificação; execute verify novamente.")
    if not sensor.get("passed") or security.get("findings"):
        raise ValueError("Verificação final reprovada.")
    paths = changed_paths(root, meta["base_commit"])
    sensitive = sensitive_paths(paths, _strings(config.get("lean", {}).get("critical_paths", []), "critical_paths"))
    risk = "critical" if meta["risk"] == "critical" or sensitive else "standard"
    if verification.get("changed_paths") != paths or verification.get("risk") != risk or verification.get("language_required") != language_required(paths):
        raise ValueError("Aplicabilidade inconsistente; execute verify novamente.")
    review = read_object(Path(args.review).expanduser().absolute())
    validate_review(review, verification, contract, meta["builder"], "reviewer")
    critical = verification["risk"] == "critical" or review["risk"] == "critical"
    evaluation = review
    if critical:
        if not args.evaluation:
            raise ValueError("Mudança sensível exige um avaliador independente adicional (--evaluation).")
        evaluation = read_object(Path(args.evaluation).expanduser().absolute())
        validate_review(evaluation, verification, contract, meta["builder"], "evaluator")
        if evaluation["reviewer"].strip().casefold() == review["reviewer"].strip().casefold():
            raise ValueError("Avaliador e code reviewer precisam ser independentes.")
    # A structured attestation is retained separately; the legacy parser still
    # enforces project-specific finding policy, including P2 when configured.
    cli.write_json(folder / "review.json", review)
    if critical:
        cli.write_json(folder / "evaluation.json", evaluation)
    text = "Revisão independente aceita; evidência detalhada em lean/review.json.\n"
    findings = review["findings"] + (evaluation["findings"] if critical else [])
    text += "\n".join(f"[{f['severity']}] {f['message']}" for f in findings)
    cli.write_text(folder / "code-review.md", text)
    language_author = evaluation if evaluation["ptbr"]["status"] == "pass" else review
    language = language_author["ptbr"]
    applicability = {
        "source_digest": verification["source_digest"], "ptbr": language,
        "risk": "critical" if critical else "standard",
        "review_mode": "parallel_independent" if critical else "combined_independent",
        "time_budget": "enforced" if critical else "advisory",
    }
    cli.write_json(folder / "applicability.json", applicability)
    if language["status"] == "pass":
        _call(cli, root, "ptbr-review", args.task_id, "--status", "pass", "--reviewer", language_author["reviewer"], "--notes", language["evidence"])
    original = read_object(run_dir / "run.json")
    updated = {**original, "budget": dict(meta["original_budget"])}
    updated["budget"]["ptbr_review_required"] = language["status"] == "pass"
    if not critical:
        updated["budget"].update(time_budget_minutes=0, timeout_minutes=0, max_fix_attempts=None)
    # Scope applicability to this run, never edit global/project policies.
    updated["lean_applicability"] = applicability
    cli.write_json(run_dir / "run.json", updated)
    try:
        _call(cli, root, "evaluate", args.task_id, "--status", "pass", "--evaluator", evaluation["reviewer"], "--notes", evaluation["notes"], "--reviewer", review["reviewer"], "--review-file", str(folder / "code-review.md"))
    except BaseException:
        cli.write_json(run_dir / "run.json", original)
        raise
    _call(cli, root, "report", args.task_id)
    print("Runvero: entrega aprovada com evidências. Nenhum merge ou deploy foi executado.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Runvero: regras antes, implementação direta, evidências no final.")
    parser.add_argument("--repo", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare", help="Prepara tarefa, contrato, contexto e run sem fila obrigatória")
    prepare.add_argument("title")
    prepare.add_argument("--body")
    prepare.add_argument("--builder", required=True)
    prepare.add_argument("--criteria", action="append", required=True)
    prepare.add_argument("--sensor", action="append", required=True)
    prepare.add_argument("--quick-sensor", action="append", default=[])
    prepare.add_argument("--architecture-sensor", action="append", default=[])
    prepare.add_argument("--required-doc", action="append", default=[])
    prepare.add_argument("--out", action="append", default=[])
    prepare.add_argument("--risk", choices=("standard", "critical"), default="standard")
    prepare.add_argument("--reviewed-sensors", action="store_true")
    for action in ("check", "verify"):
        command = sub.add_parser(action)
        command.add_argument("task_id")
    finish = sub.add_parser("finish", help="Valida parecer independente e aplica os gates existentes")
    finish.add_argument("task_id")
    finish.add_argument("--review", required=True)
    finish.add_argument("--evaluation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo.expanduser().resolve()
    started = time.monotonic()
    can_record = False
    outcome = "error"
    try:
        cli = _legacy()
        if not root.is_dir():
            raise ValueError("O repositório precisa existir.")
        cli.require_safe_branch(root, argparse.Namespace(allow_main=False), "runvero")
        can_record = True
        with cli.state_lock(root, "lean-workflow"):
            if args.action == "prepare":
                _prepare(cli, root, args)
            elif args.action == "finish":
                _finish(cli, root, args)
            else:
                _verify(cli, root, args)
        outcome = "ok"
        return 0
    except SystemExit as exc:
        if exc.code not in (None, 0):
            print(f"Runvero: {exc}", file=sys.stderr)
            return 2
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f"Runvero: {exc}", file=sys.stderr)
        return 2
    finally:
        # Command wall time includes tests and optional observation; it is not
        # model inference time or a claim about tokens, accuracy or savings.
        duration_ms = round((time.monotonic() - started) * 1000)
        if can_record and (root / ".harness/config.json").exists():
            try:
                cli.append_harness_event(root, "lean_stage_completed", {
                    "stage": args.action, "outcome": outcome, "duration_ms": duration_ms,
                    "task_id": getattr(args, "task_id", None),
                }, source="runvero")
            except Exception:
                print("Não foi possível registrar a duração; confira o resultado acima.", file=sys.stderr)
        print(f"Runvero {args.action}: {duration_ms / 1000:.2f}s", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
