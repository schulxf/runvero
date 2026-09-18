---
name: harness-runner
description: "Use quando trabalho planejado em repo precisar passar pelo protocolo Harness v0.3: queue, contrato, supervisor, checkpoints/resume, TDD com escopo limitado, sensores deterministicos revisados, avaliador spawnado, reviewer Greptile-style, security scan, artefatos, Telegram remote control, GitHub helpers e relatorio final com memoria de projeto."
---

# Harness Runner

Use o Harness Runner como camada operacional ao redor das skills de
planejamento e codigo. Nao substitua Grillme, PRD, issues ou TDD. Coloque
essas etapas em um protocolo repetivel.

v0.3 e local-first: dashboard, pixel-art hub multi-repo, queue, supervisor,
checkpoints, artifact viewer, project memory, plugin registry, security scanner e Telegram remote control sao
superficies sobre o mesmo estado `.harness/`.

## Graph Engineering

Use a skill `$graph-engineering` como especialista quando a task envolver
ontologia, extracao de entidades ou relacoes, fusao de entidades, GraphRAG,
memoria semantica ou um grafo explicito de trabalho multiagente. Nao a invoque
para bugs, features e refactors comuns que nao precisam dessas estruturas.

Graph Engineering define o modelo e a topologia; o Harness continua responsavel
por contrato, queue, run, checkpoints, sensores, budgets e gates finais. A skill
nao e um plugin executavel nem substitui o supervisor. Em grafos de tarefas,
mantenha uma implementacao ativa por repo e use paralelismo apenas para handoffs
independentes ou revisoes, com um unico dono da consolidacao.

## CLI

Caminho local padrao depois de clonar este repo:

```powershell
<harness-schulx>\bin\harness.py
```

Use um caminho real e existente de repo via variavel. Nao rode placeholders
literais:

```powershell
$HARNESS = "C:\path\to\harness-schulx\bin\harness.py" # trocar pelo caminho real
$APP_REPO = "C:\path\to\your-app" # trocar por um repo real existente
Test-Path -LiteralPath $APP_REPO
python $HARNESS --repo $APP_REPO <comando>
```

`init` nao cria o diretorio do repo por padrao. Use `init --create` apenas
quando a criacao for intencional.

## Compatibilidade

`bin/harness.py` e a sintaxe documentada nesta skill sao superficie publica. Se
o Harness for refatorado, esse entrypoint deve continuar funcionando.

Antes de confiar numa instalacao nova ou numa branch refatorada, rode:

```powershell
python $HARNESS compat manifest
python $HARNESS compat skill-smoke
```

`compat skill-smoke` cria um repo falso em diretorio temporario e executa o
fluxo principal da skill pelo entrypoint publico. Se falhar, nao use a branch
para trabalho autonomo ate corrigir a compatibilidade.

## Seguranca De Branch

Comandos que escrevem arquivos ou rodam sensores sao bloqueados em `main`,
`master` e `production`. Crie uma branch de trabalho primeiro:

```powershell
git -C $APP_REPO switch -c harness/TASK-001
```

Se a excecao for intencional, passe `--allow-main` antes do comando:

```powershell
python <harness.py> --repo $APP_REPO --allow-main init
```

## Fluxo Diario

1. Ao assumir o papel de implementador, adicione imediatamente o caminho absoluto do repo alvo ao painel central de acompanhamento.
2. Se o repo alvo nao tiver `.harness/config.json`, rode `init`.
3. Configure `required_context` em `.harness/config.json`.
4. Ingira docs de contexto, PRD, arquitetura e ADR do repo alvo.
5. Rode `preflight` para confirmar que o contexto obrigatorio foi ingerido e nao mudou.
6. Importe ou crie uma task a partir de issue, queue item ou GitHub Issue.
7. Coloque a task na queue com profile e budget quando essa superficie existir.
8. Crie um contrato antes da implementacao.
9. Inicie uma run pelo supervisor ou CLI e leia `builder-brief.md`.
10. Implemente apenas essa task, preferencialmente usando `tdd`.
11. Salve checkpoints depois de progresso relevante ou antes de pausar.
12. Rode sensores revisados e preserve o resultado.
13. Gere handoffs com `evaluate <task_id>`.
14. Spawn um avaliador com `fork_context=false` usando apenas `evaluator-agent-handoff.md`.
15. Spawn um reviewer Greptile-style com `fork_context=false` usando apenas `greptile-reviewer-agent-handoff.md`.
16. Rode `security scan --task-id <task_id>` e preserve o relatório da run.
17. Revise ortografia, acentuação e clareza em PT-BR e registre com `ptbr-review`.
18. Consolide os sinais usando `review-consolidation.md`.
19. Registre a decisão com `evaluate <task_id> --status ... --review-file ...`.
20. Gere `report <task_id>` e alimente memória de projeto com o resumo aprovado.

### Regra de visibilidade do implementador

- O registro no painel acontece antes da primeira alteração de código da implementação.
- `start` e `supervisor tick|run --auto-start` registram automaticamente o repo no painel central.
- `agent register --role builder|developer|implementer|coder` também registra o repo automaticamente.
- Use `HARNESS_HUB_CONTROL_REPO` para apontar explicitamente o repo de controle do painel. No Windows, sem essa variável, o Harness procura `%LOCALAPPDATA%\HarnessAcompanhamento\control`.
- Em automações isoladas que não podem alterar o painel local, use `HARNESS_HUB_CONTROL_REPO=disabled`.
- O registro é idempotente: o mesmo caminho não é duplicado.
- Um projeto ocultado pela pessoa usuária permanece oculto. Se tiver sido removido do painel, ele volta a ser adicionado na próxima ativação como implementador.
- Falha de acesso ao painel gera um aviso claro, mas não apaga arquivos nem altera o escopo da task.

## v0.3 Superficies

- dashboard local: queue, run ativa, sensores, checkpoints, budget e artefatos;
- pixel-art hub: mapa multi-repo para acompanhar agentes e tarefas em salas operacionais;
- task queue: uma task ativa por repo, outras em `planned`, `ready`, `blocked` ou `done`;
- supervisor: aplica policy, inicia runs, salva checkpoints e bloqueia transicoes inseguras;
- resume/checkpoints: retomar pela ultima evidencia em `.harness`, nao pela memoria do chat;
- GitHub helpers: importar Issues, sugerir branch, montar PR body e criar follow-ups;
- budgets/profiles: `fast`, `standard`, `deep`;
- artifact viewer: indexar reports, logs, screenshots, handoffs, midias e scans;
- failure policy: contexto stale, sensor final falho, avaliador FAIL, P0/P1 e security critical bloqueiam;
- project memory: docs obrigatorios, ADRs, contratos, reports, summaries e decisoes aceitas;
- plugin registry: integra GitHub, Telegram, security scanner, browser, CI e renderers;
- security scanner: checa secrets, shell unsafe, writes fora do repo, permissoes e artifacts compartilhaveis;
- Telegram: remote control para status, queue, checkpoint, artifacts, report e `/codex`.

Quando uma instalacao ainda nao expuser um comando especifico, registre o mesmo
estado em arquivos `.harness` ou artefatos da run e deixe claro no relatorio
como retomar.

## Configuracao

Configure documentos globais obrigatorios em `.harness/config.json`:

```json
{
  "required_context": [
    { "path": "AGENTS.md", "kind": "context" },
    { "path": "CONTEXT.md", "kind": "domain-context" },
    { "path": "docs/adr/ADR-000-indice-e-principios.md", "kind": "adr" }
  ],
  "evaluation_policy": {
    "mode": "spawned_agent",
    "fork_context": false,
    "input_scope": "evaluator_agent_handoff"
  },
  "review_policy": {
    "enabled": true,
    "mode": "spawned_agent",
    "fork_context": false,
    "skill": "greptile-review",
    "input_scope": "greptile_reviewer_handoff",
    "blocking_findings": {
      "p0": true,
      "p1_in_changed_surface": true,
      "p2": false
    }
  },
  "profiles": {
    "default": "standard",
    "fast": { "sensor_tier": "quick", "security_scan": "optional" },
    "standard": { "sensor_tier": "full", "security_scan": "required" },
    "deep": { "sensor_tier": "full", "security_scan": "required", "extra_review": true }
  }
}
```

Tipos aceitos em `--kind`: `context`, `domain-context`, `prd`, `issue`,
`architecture`, `infrastructure`, `security`, `testing`, `refactor-plan`,
`decision`, `adr`, `guardrail`, `other`.

## Comandos Base

Inicializar:

```powershell
python <harness.py> --repo $APP_REPO init
```

Ingerir docs:

```powershell
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\context.md" --kind context
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\prd.md" --kind prd
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\architecture.md" --kind architecture
python <harness.py> --repo $APP_REPO ingest "$APP_REPO\docs\adr\ADR-000-indice-e-principios.md" --kind adr
python <harness.py> --repo $APP_REPO preflight
```

Importar ou criar task:

```powershell
python <harness.py> --repo $APP_REPO task import "$APP_REPO\issues\001-login.md"
python <harness.py> --repo $APP_REPO task create "Titulo curto da task" --body "O que construir"
```

Criar contrato:

```powershell
python <harness.py> --repo $APP_REPO contract TASK-001 `
  --criteria "comportamento observavel" `
  --smoke-sensor "npm test -- login" `
  --affected-sensor "npm run typecheck" `
  --full-sensor "npm test" `
  --full-sensor "npm run build" `
  --reviewed-sensors `
  --required-doc "docs/adr/ADR-000-indice-e-principios.md" `
  --out "item fora de escopo"
```

Use `--reviewed-sensors` apenas depois de ler os comandos. Caso contrario,
confirme depois com `sensors --reviewed`.

Iniciar:

```powershell
python <harness.py> --repo $APP_REPO start TASK-001
```

`start` roda `preflight TASK-001` automaticamente. Se um documento obrigatorio
mudou desde o ultimo `ingest`, reingira o arquivo antes de iniciar. Use
`--skip-preflight` apenas para excecao consciente.

Rodar sensores:

```powershell
python <harness.py> --repo $APP_REPO sensors TASK-001 --tier quick --reviewed
python <harness.py> --repo $APP_REPO sensors TASK-001 --tier full --reviewed
```

Use `quick-pass TASK-001 --reviewed` para rodar a camada rapida e gerar
handoffs. Use `full-pass TASK-001 --reviewed` para a rodada final.

Sensores rodam sem shell por padrao. Use `--allow-shell` apenas quando um
comando revisado depender de comportamento de shell.

A revisão é vinculada ao digest do tier, da lista exata de comandos e do modo
de shell. Qualquer override diferente exige uma nova confirmação `--reviewed`.

## Avaliacao E Revisao

Criar brief e handoffs:

```powershell
python <harness.py> --repo $APP_REPO evaluate TASK-001
```

Isso cria `evaluator-brief.md`, `evaluator-agent-handoff.md`,
`greptile-reviewer-agent-handoff.md`, `review-consolidation.md` e
`parallel-dispatch.md` na ultima run.

Use cada handoff como unica entrada para seu respectivo agente spawnado sem
contexto da sessao atual:

```text
spawn_agent:
- agent_type: default
- fork_context: false
- mensagem: conteudo ou caminho do evaluator-agent-handoff.md

spawn_agent:
- agent_type: default
- fork_context: false
- mensagem: conteudo ou caminho do greptile-reviewer-agent-handoff.md
```

Se `spawn_agent` nao estiver disponivel, use uma nova sessao manual com somente
o conteudo do handoff correspondente. Nao repasse historico ou decisoes
informais do implementador.

Consolidacao:

- o avaliador contratual decide se a task cumpre contrato, sensores e evidencia;
- o reviewer Greptile-style decide se o diff introduz risco tecnico;
- o security scanner decide se houve vazamento, permissao perigosa ou artefato inseguro;
- `FAIL` do avaliador bloqueia;
- `P0` do reviewer bloqueia;
- `P1` dentro da superficie alterada normalmente bloqueia;
- finding critical de seguranca bloqueia;
- `P2` nao bloqueia por padrao; vira ajuste opcional ou follow-up.

Se houver P0/P1 bloqueante, gere fix brief na mesma task:

```powershell
python <harness.py> --repo $APP_REPO fix-brief TASK-001 --review-file reviewer-output.md
```

Depois corrija o menor trecho necessario, rode `sensors --tier quick`, gere
handoffs de novo e finalize apenas depois de `sensors --tier full`.

Registrar decisao:

```powershell
python <harness.py> --repo $APP_REPO security scan --task-id TASK-001 --fail-on-findings
python <harness.py> --repo $APP_REPO ptbr-review TASK-001 --status pass --notes "Ortografia, acentuação e clareza conferidas."
python <harness.py> --repo $APP_REPO evaluate TASK-001 --status pass --notes "Evidência aceita." --review-file reviewer-output.md
python <harness.py> --repo $APP_REPO evaluate TASK-001 --status fail --gap "Falta teste de persistencia."
```

Gerar relatorio:

```powershell
python <harness.py> --repo $APP_REPO report TASK-001
```

O fechamento cria ou atualiza `.harness\runs\<task>\<run>\plain-summary.md`.

## Telegram

Configure o token fora do repo:

```powershell
$env:HARNESS_TELEGRAM_BOT_TOKEN = "<telegram-bot-token>"
```

Habilite notificacoes e chats autorizados:

```powershell
python <harness.py> --repo $APP_REPO telegram configure `
  --enable `
  --chat-id "123456789" `
  --allowed-chat-id "123456789"
```

Comandos uteis:

```powershell
python <harness.py> --repo $APP_REPO telegram status
python <harness.py> --repo $APP_REPO telegram send "Harness conectado."
python <harness.py> --repo $APP_REPO telegram listen
python <harness.py> --repo $APP_REPO telegram codex --resume-last
python <harness.py> --repo $APP_REPO telegram mirror
python <harness.py> --repo $APP_REPO telegram bridge --include-tools
```

Use `telegram mirror` para acompanhar uma sessao Codex CLI sem interromper o
turno ativo. Use `telegram bridge --include-tools` para acompanhar a sessao
ativa e receber mensagens no mesmo processo. Por padrao, mensagens comuns ficam
em `.harness/telegram/operator-messages.md`; use `/codex <mensagem>` quando
quiser chamar `codex exec resume --last` em paralelo.

No Telegram:

```text
/help
/status
/tasks
/queue
/active
/checkpoint
/artifacts TASK-001
/budget
/pick
/report TASK-001
/new descreva a nova tarefa
/codex mande esta mensagem direto para o Codex
```

Mensagens normais, imagens e audios entram em `.harness/inbox/telegram/`.
Midias sao salvas em `.harness/inbox/telegram/media/`.

## Regras Operacionais

- Trabalhe em uma task por vez.
- Use queue/supervisor quando disponivel; se nao estiver disponivel, emule o estado no protocolo local.
- ADRs e docs obrigatorios ficam no repo alvo como fonte da verdade.
- Nao inicie run se `preflight` falhar por contexto ausente ou desatualizado.
- Trate `.harness/contracts/<task>.json` como vinculante.
- Salve checkpoints antes de pausar, trocar de agente, rodar revisao longa ou pedir decisao humana.
- Resuma pela ultima evidencia em `.harness`, nao por lembranca do chat.
- Nao expanda escopo a partir de comentarios do avaliador.
- Não marque task como concluída sem sensores, security scan, revisão PT-BR e parecer do reviewer.
- Prefira sensores deterministicos antes de revisao semantica.
- O implementador pode se auto-checar, mas nao deve se autoaprovar; use sempre um agente avaliador separado.
- O reviewer Greptile-style revisa risco do diff, nao substitui o avaliador contratual.
- Use `review-consolidation.md`: `FAIL`, `P0`, `P1` na superficie alterada e security critical bloqueiam.
- Use security scanner vinculado à run antes do pass em todos os profiles padrão.
- Se os auxiliares do GitHub estiverem configurados, use `github pr-create` apenas depois dos gates finais; ele grava a descrição e o comentário simples em `.harness/github`, cria o PR e garante um único comentário sanitizado.
- Plugins devem declarar comandos, arquivos escritos, acesso de rede e secrets usados.
- Se sensores falharem, crie o menor fix brief possivel e rode novamente.
- Guarde progresso em `.harness`, nao so na memoria do chat.
- Versione no maximo `.harness/config.json`, `.harness/progress.md`, `.harness/tasks/**`, `.harness/contracts/**`, `.harness/reports/**` e memoria compacta aprovada.
- Mantenha `.harness/runs/**`, `.harness/context/**`, avaliacoes, logs, screenshots, inbox, midias e outputs grandes locais.

## Prompt De Handoff

Quando pedirem para implementar a proxima issue, use este formato:

```text
Vou rodar o Harness para uma issue:
1. escolher/importar a task
2. colocar na queue com profile/budget quando disponivel
3. criar ou verificar o contrato
4. iniciar uma run pelo supervisor ou CLI
5. implementar com TDD
6. salvar checkpoints
7. rodar sensores revisados
8. criar brief/handoffs do avaliador e do reviewer Greptile-style
9. spawnar avaliador sem contexto da sessao atual
10. spawnar reviewer Greptile-style sem contexto da sessao atual
11. rodar security scan vinculado à run
12. revisar ortografia, acentuação e clareza em PT-BR
13. consolidar sinais e registrar avaliação/relatório com o parecer do reviewer
```
