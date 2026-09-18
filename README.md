# Runvero

**Project rules before implementation. Verifiable evidence before approval.**

[![Tests](https://github.com/schulxf/runvero/actions/workflows/tests.yml/badge.svg)](https://github.com/schulxf/runvero/actions/workflows/tests.yml)
[![Skill compatibility](https://github.com/schulxf/runvero/actions/workflows/compat.yml/badge.svg)](https://github.com/schulxf/runvero/actions/workflows/compat.yml)
[![JEV observer](https://github.com/schulxf/runvero/actions/workflows/jev-observer.yml/badge.svg)](https://github.com/schulxf/runvero/actions/workflows/jev-observer.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)

Runvero is a local-first workflow for AI-assisted development. It gives the coding
agent a clear task and the application's rules, lets the agent implement directly,
and checks the result before recording approval. An optional JEV observer helps
investigate failed checks without taking control of the implementation.

Previously named **Harness Schulx**. Existing `bin/harness.py`, `harness-schulx`
and `.harness/` interfaces remain compatible; the lean checkout entrypoint is
`bin/runvero.py`.

[Quick start](#quick-start) · [Workflow](#workflow) · [JEV](#jev-failure-observer) ·
[Full protocol](#full-protocol-and-optional-surfaces) · [Documentation](#documentation)

## Why Runvero

The goal is not to micromanage every edit or add a review meeting after every test.
It is to make four things explicit: the expected result, the rules that constrain
the change, the checks that actually ran, and the independent review of the code.

| Capability | Purpose |
|---|---|
| Short preparation | Reuse the goal, criteria and project documents without a mandatory queue/supervisor ritual. |
| Direct implementation | Let the coding agent investigate, edit and run quick checks without repeated reviewer dispatch. |
| Architectural checks | Include the project's real structural checks in the mandatory final sensor plan. |
| Independent final review | Use one combined reviewer normally; require a separate evaluator for sensitive changes. |
| Current evidence | Reject old reviews, changed contracts, failed checks and evidence for a different source state. |
| JEV observer | Suggest investigation of environment blockers or repeated failures; never approve or execute actions. |

Reading an ADR is not proof that code follows it. Runvero runs the architectural
checks you configure and requires an architectural review; it does not infer or
prove all application rules automatically.

## Quick start

The Python core has no external runtime package dependencies. Use Python 3.10+
and Git. The application needs its own test tools. Node.js and Gateway credentials
are needed only for the optional JEV integration.

```powershell
git clone https://github.com/schulxf/runvero.git
cd runvero
$RUNVERO = "$PWD\bin\runvero.py"
$APP = "C:\path\to\your-app"

python $RUNVERO --help
git -C $APP switch -c feature/fix-registration
```

Start from a clean application worktree. Replace these sample commands with real
scripts in the application, inspect them, and then confirm the sensor plan:

```powershell
python $RUNVERO --repo $APP prepare "Fix registration persistence" `
  --builder "builder-session-1" `
  --criteria "A valid registration remains saved after reloading" `
  --criteria "Invalid input is not persisted" `
  --required-doc "docs/architecture.md" `
  --sensor "npm run test:registration" `
  --sensor "npm run typecheck" `
  --architecture-sensor "npm run check:architecture" `
  --quick-sensor "npm run test:registration" `
  --out "Changing the authentication provider" `
  --reviewed-sensors
```

`prepare` initializes `.harness/` when needed and uses the existing task, contract,
context and run machinery. It includes a root `AGENTS.md` when present, plus
configured and explicitly required documents. No task starts without a rules
document. Read the generated `builder-brief.md` and let the coding agent implement.

```powershell
# Optional during implementation: checks only, no reviewer handoffs.
python $RUNVERO --repo $APP check TASK-001

# Once the implementation is coherent: final sensors, secret scan and review input.
python $RUNVERO --repo $APP verify TASK-001
```

Open the generated `lean/review-handoff.md` in a fresh review session. The reviewer
fills the `review-request.json` template with a real decision and evidence, saving
it as `review.json` in that run's `lean/` directory. The template does not approve
anything by default.

```powershell
python $RUNVERO --repo $APP finish TASK-001 `
  --review "$APP\.harness\runs\TASK-001\<RUN>\lean\review.json"
```

Replace `<RUN>` with the actual execution directory. `finish` validates the review
and applies the existing completion gates. It does not merge, deploy or publish.
For a sensitive change, also supply `--evaluation` with a second independent
assessment. The [lean workflow guide](docs/LEAN_WORKFLOW.md) describes the format,
escalation rules, architectural checks and migration boundaries.

## Workflow

```text
Goal + criteria + relevant project rules
                   |
                 prepare
                   |
       Coding agent implements directly
          + quick checks as needed
                   |
                 verify
       final sensors + secret scan
                   |
          Independent final review
       + separate evaluator when critical
                   |
                 finish
       current evidence + existing gates
                   |
          Recorded decision and report
```

### Clear responsibilities

**The coding agent** implements, investigates and tests within the agreed scope.
It must request a decision before changing architectural constraints, expanding
scope or performing sensitive operations.

**Runvero** prepares the context, runs reviewed commands, binds evidence to the
source state and validates the final attestation. It does not implement the feature
or automatically spawn an approval panel.

**The independent reviewer** checks both acceptance criteria and technical risk,
including the architecture. Sensitive changes require another independent evaluator.
The implementer cannot be declared as either approver.

**JEV** provides advisory failure signals. Its outputs are hypotheses, not proof
that a diagnosis is correct or a task is complete.

### Proportional review, not weaker evidence

The lean workflow removes mandatory queue management, intermediate reviewer
dispatch and repeated manual record keeping from ordinary tasks. Final reviewed
sensors, a secret scan and an independent review still apply.

Sensitive paths and project-specific patterns trigger additional review. A reviewer
can also escalate risk based on the actual code. Path heuristics are conservative
hints, not a semantic risk classifier.

PT-BR review may be explicitly `not_applicable`, with a reason, when no relevant
text changed. Documentation, interface and translation changes require actual
review. A skipped language check is never written as a fake passing review.

Time and fix-attempt budgets are advisory for standard lean tasks; critical tasks
retain their original enforced budget. These changes are scoped to the run,
not applied by disabling project-wide policies. Command wall times are recorded
as `lean_stage_completed` events for comparison, without fabricated savings or
model accuracy claims.

## JEV failure observer

JEV remains **optional, disabled by default and advisory-only**. After explicit
project consent, the default automatic trigger is now a **failed sensor execution**.
Successful checks do not collect JEV context, start its Node process or spend an
API call.

| `automatic_trigger` | Behavior |
|---|---|
| `failures` | Default: observe failed sensor invocations. |
| `manual` | Use explicit preview/observe/status commands only. |
| `always` | Restore automatic observation after every boolean sensor result. |

The existing redaction, timeouts, call budgets, deduplication and stale-response
checks remain in place. A failed observation does not change test results or
relax approval policy. Calls on the failure path are still synchronous and bounded;
this is not a zero-latency or background-monitoring claim.

Read [JEV_OBSERVER.md](docs/JEV_OBSERVER.md) for installation and privacy, and the
[JEV section of the lean guide](docs/LEAN_WORKFLOW.md#jev-continua-disponível) for
trigger configuration. Preview the data before enabling remote transmission.
No credentials or managed-project settings are changed by this repository update.

## Full protocol and optional surfaces

The original CLI remains available for queue-driven work, long sessions,
checkpoints, resumption, explicit replanning and project-specific operating policies:

```powershell
python .\bin\harness.py --help
python .\bin\harness.py compat manifest
python .\bin\harness.py compat skill-smoke
```

The full protocol's command surface and default profiles are unchanged. Existing
runs are not migrated into the lean workflow automatically.

The local dashboard, multi-project hub, Telegram remote control, GitHub helpers,
artifact viewer, project memory and plugin registry remain optional capabilities.
They do not need to become administrative prerequisites for every new task.
Remote execution and sensitive actions still require their separate permissions.

The bundled [Harness Runner skill](skills/harness-runner/SKILL.md) routes ordinary
work to the lean workflow and loads the [complete protocol](skills/harness-runner/references/full-workflow.md)
only when needed. The bundled [Graph Engineering skill](skills/graph-engineering/SKILL.md)
is for genuinely graph-shaped tasks, not a mandatory implementation dependency.
Its upstream attribution and license remain in that directory.

## Repository layout

```text
bin/runvero.py                  Lean checkout entrypoint
bin/harness.py                  Compatible full-protocol CLI
harness_core/lean.py            Preparation and final-validation adapter
harness_core/jev_trigger.py     Cheap automatic-observer trigger policy
harness_core/                   Existing tasks, evidence, policies and integrations
integrations/jev-worker/        Optional JEV Gateway worker
hub/                           Optional multi-project hub
skills/                        Agent workflow guidance
docs/                          Operating guides and design documents
tests/                         CLI, policy, integration and regression tests
```

Application state stays in `.harness/`. Keep copied context, run evidence, logs and
credentials out of public commits unless intentionally reviewed for sharing.

## Documentation

| Guide | Contents |
|---|---|
| [Lean workflow](docs/LEAN_WORKFLOW.md) | Preparation, implementation, verification, review format, escalation and JEV. |
| [Full protocol](docs/HARNESS_PROTOCOL.md) | Existing task lifecycle and completion gates. |
| [v0.3 operating model](docs/V0_3_HARNESS.md) | Queue, supervisor, checkpoints, budgets and optional surfaces. |
| [JEV observer](docs/JEV_OBSERVER.md) | Optional installation, consent, privacy and model-integration limits. |
| [Legacy speed loop](docs/SPEED_LOOP.md) | Quick/full sensor tiers and parallel review in the full protocol. |
| [Telegram](docs/TELEGRAM.md) | Bot setup, authorized chats and remote modes. |
| [Accompaniment UI](docs/HARNESS_ACOMPANHAMENTO_UI.md) | Multi-project monitoring and interface behavior. |
| [Contributing](CONTRIBUTING.md) | Development practices and checks. |

## Development

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check bin/harness.py bin/runvero.py harness_core tests
python -m pytest tests/ --cov=harness --cov=harness_core --cov-report=term-missing
node --test integrations/jev-worker/worker.test.mjs
```

The JEV tests use simulated providers and do not establish live model accuracy,
latency or productivity gains. Measure representative work before expanding
model-driven supervision.

## Trust boundaries

Runvero validates evidence and review attestations; it is not a sandbox or an
authenticated agent-identity system. A writer to `.harness/` can modify local
records. Use genuinely independent review sessions and retain CI/branch protections
and explicit production approvals. Keep secrets in environment variables, inspect
sensor commands before reviewing them, and never treat redaction as complete
prevention of private-data exposure.
