---
name: harness-runner
description: "Use para implementar mudanças respeitando regras do projeto: preparação curta, implementação direta, testes e revisão independente proporcional ao risco. JEV auxilia diagnósticos de falhas. O fluxo completo permanece disponível para fila, retomada e trabalhos longos."
---

# Runvero — regras antes, evidências depois

Não imponha o protocolo completo a toda implementação. Use o fluxo enxuto por
padrão para uma mudança coerente. O agente implementa; o Runvero prepara contexto
e aplica verificações. Não confunda menos etapas com menos evidência.

## Fluxo normal

Use um checkout completo e caminhos reais. O entrypoint novo é `bin/runvero.py`.
O entrypoint público anterior `bin/harness.py` e seus comandos continuam disponíveis.

1. Entenda o objetivo, os critérios e as regras da aplicação. Reutilize o plano
   aprovado em vez de recriá-lo. Prepare a tarefa em uma branch/worktree limpa.
2. Execute `prepare` com critérios, identidade do implementador, documentos e
   scripts reais revisados. Leia o `builder-brief.md` produzido.
3. Implemente diretamente e teste durante o trabalho. `check` dá feedback sem
   criar handoffs. Não convoque avaliadores a cada teste bem-sucedido.
4. Quando o diff estiver coerente, execute `verify`. Abra uma sessão independente
   para revisar contrato, arquitetura, diff completo e evidências. Não herde as
   conclusões do implementador nem limite a revisão a caminhos pré-selecionados.
5. Use `finish` somente depois de obter um parecer real e completo. Nunca preencha
   campos de aprovação apenas para satisfazer o CLI. Corrija problemas relevantes
   e repita somente o trabalho necessário antes de nova verificação final.

```powershell
$RUNVERO = "C:\ferramentas\runvero\bin\runvero.py"
$APP_REPO = "C:\projetos\app"
python $RUNVERO --repo $APP_REPO prepare "Objetivo da mudança" `
  --builder "identidade-da-sessao-implementadora" `
  --criteria "Resultado observável" `
  --required-doc "docs/architecture.md" `
  --sensor "npm run test:affected" `
  --architecture-sensor "npm run check:architecture" `
  --reviewed-sensors
python $RUNVERO --repo $APP_REPO check TASK-001
python $RUNVERO --repo $APP_REPO verify TASK-001
```

Adapte os comandos aos scripts existentes. A confirmação de sensores exige
leitura real. Arquivos de regras orientam o modelo; não demonstram conformidade
por si só. Verificadores arquiteturais e revisão do código continuam importantes.

O handoff final fica em `.harness/runs/<TASK>/<RUN>/lean/review-handoff.md`.
O modelo JSON de parecer começa com `needs-work` e `not_checked`. O reviewer deve
preencher evidências e salvar seu parecer dentro da pasta da execução. Então:

```powershell
python $RUNVERO --repo $APP_REPO finish TASK-001 --review "<caminho-real-do-review.json>"
```

O autor do parecer não pode ser o implementador. Identidades declaradas não
comprovam isolamento; o operador precisa realmente usar sessões separadas.

## Risco e limites

Use `prepare --risk critical` para mudanças sensíveis. Caminhos críticos também
podem promover o risco automaticamente, mas são apenas dicas conservadoras. O
reviewer deve promover para `critical` quando houver risco semântico, mesmo em um
diff pequeno ou caminho aparentemente comum. Nesse caso, obtenha outro parecer
independente com `role: evaluator`, em paralelo quando possível, e forneça
`finish --evaluation <arquivo>`.

Não remova testes, afrouxe políticas, altere ADRs ou mude permissões para forçar
aprovação. Diante de conflito arquitetural, ampliação de escopo ou operação
destrutiva, peça decisão antes de agir. Não trate revisão posterior como
substituição de sandbox, controle de segredos ou autorização de produção.

Revisão PT-BR não aplicável exige justificativa, não um `pass` inventado. Mudanças
em documentos, interface e traduções exigem revisão real. Orçamento é informativo
no fluxo normal e continua aplicado em risco crítico. Testes finais, segurança e
correspondência entre código e evidências não se tornam opcionais.

## JEV

Use a integração existente como observador de falhas, com consentimento explícito
por projeto. `automatic_trigger: failures` evita chamadas nos testes verdes.
`manual` e `always` são alternativas explícitas. O modelo nunca aprova, corrige,
pausa, reinicia nem publica. Não habilite envio de logs ou use API paga sem a
configuração/consentimento do operador. Preview e chamadas manuais continuam disponíveis.

## Quando usar o fluxo completo

Para fila, supervisão operacional, retomada de sessões longas, replanejamento ou
exigências específicas do projeto, leia [o protocolo completo](references/full-workflow.md).
Não carregue esse guia no contexto de toda tarefa comum. O fluxo legado e as
regras de compatibilidade continuam válidos para suas execuções.

Hub, Telegram, memória e plugins são superfícies opcionais de acompanhamento;
não crie tarefas administrativas apenas para alimentá-las. `start` continua
registrando o projeto no painel quando configurado. Preserve
`HARNESS_HUB_CONTROL_REPO=disabled` em testes isolados.

## Graph Engineering

Use `$graph-engineering` somente em trabalho que realmente envolva grafos,
ontologia ou GraphRAG. A skill **nao e um plugin executavel** e não substitui os
gates do Runvero. Não introduza grafos para simplificar uma tarefa comum.

Guia de referência no checkout: `docs/LEAN_WORKFLOW.md`.
