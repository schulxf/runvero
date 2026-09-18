# Harness Schulx

**Local-first workflows for AI-assisted software development.**

[![Tests](https://github.com/schulxf/harness-schulx/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/schulxf/harness-schulx/actions/workflows/tests.yml)
[![Skill compatibility](https://github.com/schulxf/harness-schulx/actions/workflows/compat.yml/badge.svg?branch=main)](https://github.com/schulxf/harness-schulx/actions/workflows/compat.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)

Harness Schulx gives coding agents a repeatable workflow built around task
contracts, reviewed checks, checkpoints, and independent review. It keeps
execution state and evidence in the project repository's `.harness/` directory,
so progress can be inspected and interrupted work can be resumed without relying
on conversation history alone.

Built for supervised Codex workflows, with a Python core that has **no third-party
runtime dependencies**. GitHub, Telegram, and JEV are optional integrations—not
requirements for the local task workflow.

[Quick start](#quick-start) · [How it works](#how-it-works) · [JEV observer](#jev-observer) · [Documentation](#documentation)

## What it provides

| Capability | Purpose |
| --- | --- |
| **Scoped work** | Define goals, acceptance criteria, required context, and explicit exclusions before implementation. |
| **Recorded verification** | Run reviewed tests, type checks, and builds; retain results and the source-state evidence used for completion checks. |
| **Independent review** | Generate separate handoffs for contract evaluation and code review, with focused fix briefs for blocking findings. |
| **Continuity** | Keep task queues, checkpoints, resume plans, operating profiles, and project memory on disk. |
| **Visibility** | Follow progress through the CLI, a local multi-project hub, artifacts, and optional Telegram notifications. |
| **Optional JEV observations** | Flag possible repeated failures or environment blockers without changing task status or executing actions. |

## How it works

```text
Task + contract + project context
                |
                v
      Run + implementation brief
                |
                v
    Coding agent implements the task
       |                    ^
       v                    |
 Quick checks          Focused fixes
       |                    ^
       v                    |
 Final checks + independent review
                |
                v
   Recorded decision + final report
```

The **Harness** manages state, evidence, and policy checks. The **coding agent**
implements the task. An **evaluator** checks the contract, while a separate
**reviewer** examines code risks. Their handoffs request isolated review without
inheriting the implementer's conversation.

A run is not an approval. `start` prepares the run and its builder brief; it does
not, by itself, launch a coding agent. Likewise, `quick-pass` and `full-pass` run
checks and prepare review handoffs—they do not approve the task or spawn the
reviewers. The operator or agent host handles those steps.

The optional **JEV observer** provides advisory signals after sensor execution.
It is outside the approval path and does not supervise individual Codex tool calls.

## Quick start

### 1. Get the CLI

Use Python **3.10+**, Git, and the tools required by the project you will manage.
No Python package installation is needed to run the CLI from a checkout.

```sh
git clone https://github.com/schulxf/harness-schulx.git
cd harness-schulx
python bin/harness.py --help
```

The examples below use **PowerShell** and an existing application repository.
Replace the application path and branch name before running them. `--repo` always
points to the application being managed, not the Harness checkout.

### 2. Initialize a project

```powershell
$HARNESS = (Resolve-Path "./bin/harness.py").Path
$APP_REPO = "C:\path\to\your-app"

git -C "$APP_REPO" switch -c feature/login-validation
python "$HARNESS" --repo "$APP_REPO" init
```

Use a working branch: `main`, `master`, and `production` are protected by default.
Initialization creates `.harness/` with project configuration and local state.
Review the detected sensor commands and generated configuration before use.

### 3. Define the task and its contract

```powershell
python "$HARNESS" --repo "$APP_REPO" task create "Validate login behavior" `
  --body "Implement email/password login with clear invalid-credential feedback."

python "$HARNESS" --repo "$APP_REPO" contract TASK-001 `
  --criteria "Valid credentials authenticate the user." `
  --criteria "Invalid credentials show a clear error without authenticating." `
  --smoke-sensor "npm test -- login" `
  --affected-sensor "npm run typecheck" `
  --full-sensor "npm test" `
  --full-sensor "npm run build" `
  --reviewed-sensors `
  --out "OAuth and password recovery"
```

Use the task ID printed by `task create`; `TASK-001` is an example. The sensor
commands above assume a matching npm-based application. Replace them with real,
non-interactive checks for your project. `--reviewed-sensors` records that the
commands were reviewed; it does not inspect or approve them on your behalf.

Projects with required context should ingest those documents before starting.
For example, when the application has an `AGENTS.md`:

```powershell
python "$HARNESS" --repo "$APP_REPO" ingest "$APP_REPO\AGENTS.md" --kind context
python "$HARNESS" --repo "$APP_REPO" preflight
```

Declare task-specific documents with `contract --required-doc`; see the
[context preflight rules](docs/HARNESS_PROTOCOL.md#context-preflight).

### 4. Implement and verify

```powershell
python "$HARNESS" --repo "$APP_REPO" start TASK-001
```

Give the generated `builder-brief.md` to your coding agent and implement the
contracted change. During implementation, save checkpoints and run targeted checks:

```powershell
python "$HARNESS" --repo "$APP_REPO" checkpoint create TASK-001 `
  --summary "Login behavior implemented; verification is next." `
  --next "Run the focused login checks."

python "$HARNESS" --repo "$APP_REPO" sensors TASK-001 --tier quick --reviewed
```

When implementation is ready, collect final evidence and prepare the reviewers:

```powershell
python "$HARNESS" --repo "$APP_REPO" sensors TASK-001 --tier full --reviewed
python "$HARNESS" --repo "$APP_REPO" security scan --task-id TASK-001 --fail-on-findings
```

Inspect the results and record the required PT-BR language review with
`ptbr-review`. Its `--help` describes the status, reviewer, and notes fields;
record only work that was actually reviewed. Then prepare independent review:

```powershell
python "$HARNESS" --repo "$APP_REPO" evaluate TASK-001
```

Run the evaluator and code reviewer from the generated handoffs and record their
actual outcomes. Do not mark a task as passed simply because the commands ran.
The [protocol](docs/HARNESS_PROTOCOL.md) documents the completion gates and fix loop.

After recording the decision:

```powershell
python "$HARNESS" --repo "$APP_REPO" report TASK-001
python "$HARNESS" --repo "$APP_REPO" status
```

## Verification and completion

A **sensor** is a command whose result can be recorded, such as a test, type check,
or build. The CLI runs the commands defined in the contract; it does not assume
that one test framework fits every project.

| Tier | Use |
| --- | --- |
| `smoke` | Fast, targeted checks for the behavior being changed. |
| `affected` | Checks around the affected area. |
| `full` | Final verification required by the contract. |
| `all` | All configured tiers, with duplicate commands removed. |
| `quick` | The first configured tier: `smoke`, then `affected`, then `full`. |

Sensor results are resolved chronologically among eligible attempts. A newer
failure must not be replaced by an older success. Quick checks remain preliminary
when the contract requires full verification.

Under the default policy, completion requires current final-sensor evidence,
a reviewed command plan, a clean run-bound security scan, PT-BR text review,
a contract evaluation, and code-review evidence without blocking findings.
Source changes can invalidate earlier evidence; time and fix-attempt budgets
also apply. Closing a queue item or generating a report does not bypass these gates.

See the [full protocol](docs/HARNESS_PROTOCOL.md) and
[fast feedback loop](docs/SPEED_LOOP.md) for operational details.

## JEV observer

**Optional · Disabled by default · Advisory only**

JEV can assess a bounded snapshot of the task and recent sensor evidence through
the Vercel AI Gateway. It looks for possible repeated failures, environment
blockers, and insufficient evidence. The Harness turns those signals into fixed
PT-BR recommendations for the operator.

The observer **cannot approve tasks, skip checks, execute diagnostics, stop an
agent, change permissions, or deploy code**. Missing credentials, timeouts, or
invalid responses do not relax the existing completion rules.

Before enabling remote access, inspect the request locally. Run this from the
Harness checkout, after creating a task and starting its run:

```powershell
python -m harness_core.jev_observer --repo "$APP_REPO" --task TASK-001 --action preview
```

`preview` makes no network call. Live observations require Node.js **22+**, the
optional worker dependencies, `AI_GATEWAY_API_KEY` in the environment, and explicit
consent in the managed project's configuration. The integration includes call
limits, timeouts, deduplication, secret-pattern redaction, and stale-result checks.

Redaction is not a complete privacy guarantee: test output can contain sensitive
data. Review the preview and the [JEV setup and privacy guide](docs/JEV_OBSERVER.md)
before authorizing remote state. Offline tests validate the integration and its
rules, not the model's accuracy or live latency.

Automatic model routing, semantic memory selection, autonomous diagnosis, and
`browser-qa` integration are not part of this observer.

## Monitoring and integrations

### Local hub

Follow work across repositories without reading every terminal session. From the
same PowerShell session used above, serve a local hub for the application:

```powershell
python "$HARNESS" --repo "$APP_REPO" dashboard hub-serve `
  --watch-repo "$APP_REPO" --port 8899
```

Open `http://127.0.0.1:8899/`. Add more projects with repeated `--watch-repo`
arguments or the hub's repository registry. See the
[hub guide](docs/HARNESS_ACOMPANHAMENTO_UI.md).

### Optional connections

| Integration | Role and requirements |
| --- | --- |
| **Codex** | Coding execution and session bridging require an installed, authenticated Codex CLI. Core task bookkeeping does not. |
| **GitHub** | Issue import and PR helpers use the GitHub CLI (`gh`). PR creation retains the final evidence checks. |
| **Telegram** | Notifications, authorized inbox messages, and session mirroring use a bot token. Remote execution needs separate opt-in. See the [Telegram guide](docs/TELEGRAM.md). |
| **JEV** | Advisory failure observations through the optional Node worker. See the [observer guide](docs/JEV_OBSERVER.md). |

The repository also includes [Harness Runner](skills/harness-runner/SKILL.md) and
[Graph Engineering](skills/graph-engineering/SKILL.md) agent skills. Graph
Engineering supplies graph and GraphRAG guidance; it is not an executable runtime
plugin. Its [integration reference](skills/graph-engineering/references/harness-integration.md)
and [upstream license](skills/graph-engineering/LICENSE) define the boundary with
the Harness.

## Repository and project state

```text
harness-schulx/
├── bin/                    Python CLI and PowerShell wrapper
├── harness_core/           State, policies, evidence, and shared hub assets
├── hub/                    Optional Node hub sidecar
├── integrations/jev-worker/ Optional JEV transport and protocol tests
├── docs/                   Setup guides and operating protocol
├── skills/                 Bundled agent skills
├── examples/               Example task inputs
├── tests/                  Python test suite
└── .github/                CI and PR communication workflows
```

Each managed application has its own `.harness/` directory for configuration,
tasks, contracts, runs, checkpoints, memory, reports, and integration state.
Run artifacts include implementation briefs, sensor results, review handoffs,
and plain-language summaries. JEV observations are stored separately from
approval records.

Review `.harness/.gitignore` before committing project state. Runs, copied context,
logs, and inbox media are local by default; selected protocol files and reports
may be versioned and must still be checked for sensitive content.

## Documentation

| Guide | Contents |
| --- | --- |
| [Harness protocol](docs/HARNESS_PROTOCOL.md) | Task lifecycle, evidence, completion gates, and review responsibilities. |
| [Operating model](docs/V0_3_HARNESS.md) | Queue, supervision, profiles, checkpoints, and integration boundaries. |
| [Fast feedback loop](docs/SPEED_LOOP.md) | Targeted checks, parallel review, and focused fixes. |
| [JEV observer](docs/JEV_OBSERVER.md) | Installation, consent, preview, limits, and privacy considerations. |
| [Telegram](docs/TELEGRAM.md) | Bot setup, authorized chats, notifications, and Codex bridging. |
| [Local hub](docs/HARNESS_ACOMPANHAMENTO_UI.md) | Multi-project visibility and local operation. |
| [Release checklist](docs/RELEASE_CHECKLIST.md) | Checks to complete before publishing changes. |
| [Contributing](CONTRIBUTING.md) | Development conventions and contribution expectations. |
| [Changelog](CHANGELOG.md) | Recorded project changes. |

For command options, use `python bin/harness.py --help` or append `--help` to a
command family, such as `queue`, `supervisor`, `checkpoint`, `memory`, or `plugin`.
CLI messages and several operational guides are in PT-BR.

## Development

From the Harness checkout:

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check bin/harness.py harness_core tests
python -m pytest tests/ --cov=harness --cov=harness_core --cov-report=term-missing
python bin/harness.py compat skill-smoke
```

The optional worker's offline protocol tests do not require an API key:

```sh
node --test integrations/jev-worker/worker.test.mjs
```

The Python CI runs on Windows with Python 3.10 and 3.12. The JEV workflow checks
the Node protocol and SDK export on Linux and Windows without calling a model.
These checks are not a live-provider benchmark.

Keep `bin/harness.py` compatible with the bundled Harness Runner skill. Add tests
for behavior changes and preserve the separation between implementation,
verification, and approval. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security boundaries

Keep credentials in environment variables, not in repository files or prompts.
Review sensor and plugin commands before authorizing execution, and retain the
coding agent's own sandbox and approval controls. The Harness is a workflow layer,
not a replacement for process isolation or a full security audit.

The built-in scanner checks common secret patterns; a clean scan does not prove
that a project is secure. Review public reports and PR content before sharing,
and enable remote integrations only for trusted projects and recipients.
