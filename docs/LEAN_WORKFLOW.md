# Fluxo enxuto com JEV

O Runvero separa **regras e critérios**, **implementação pelo agente** e
**validação independente**. O fluxo completo continua disponível em
`bin/harness.py`; não houve migração de dados nem alteração global das políticas.

## Escolher o fluxo

Use `bin/runvero.py` para uma mudança coerente, iniciada em uma branch/worktree
limpa. `prepare` agrupa operações determinísticas existentes; o agente não precisa
executar um ritual manual de fila, supervisor, contratos e ingestão.

O fluxo normal exige **um revisor independente**, responsável pelo atendimento
contratual e pelo risco técnico. Mudanças sensíveis exigem também um avaliador
independente adicional. Contratos, sensores finais revisados, contexto atual,
scan de segredos e a identidade do código continuam necessários.

Use o fluxo completo quando precisar de fila operacional, checkpoints de longa
duração, retomada ou replanejamento explícito. Seu comportamento e os perfis
existentes não foram alterados. A única mudança compartilhada é o gatilho
automático do JEV: falhas por padrão, configurável para o comportamento anterior.

## Preparar

Execute a partir de um checkout completo. Python 3.10+ e Git são necessários;
Node e API continuam opcionais. O novo entrypoint não depende de instalar um
pacote nem substitui o comando legado `harness-schulx`.

```powershell
$RUNVERO = "C:\ferramentas\runvero\bin\runvero.py"
$APP = "C:\projetos\minha-app"
git -C $APP switch -c feature/correcao-cadastro

python $RUNVERO --repo $APP prepare "Corrigir persistência do cadastro" `
  --builder "sessao-implementador-1" `
  --criteria "Cadastro válido permanece salvo depois de recarregar a página" `
  --criteria "Entrada inválida não é persistida" `
  --required-doc "docs/architecture.md" `
  --sensor "npm run test:cadastro" `
  --sensor "npm run typecheck" `
  --architecture-sensor "npm run check:architecture" `
  --quick-sensor "npm run test:cadastro" `
  --out "Trocar o provedor de autenticação" `
  --reviewed-sensors
```

**Adapte os scripts aos comandos reais da aplicação e revise-os antes de confirmar.**
`prepare` não instala ferramentas, não inventa scripts de arquitetura e não decide
quais testes podem ser dispensados. Os comandos fornecidos como `--sensor` e
`--architecture-sensor` integram os sensores finais obrigatórios.

O comando registra a tarefa e a execução, incorpora os documentos configurados e
escreve um brief curto em `.harness/runs/<TASK>/<RUN>/builder-brief.md`. `AGENTS.md`
da raiz é incluído quando existe. Outros documentos necessários devem estar em
`required_context` ou em `--required-doc`. Sem nenhum documento de regras, a
preparação recusa iniciar. Leitura/ingestão **não prova conformidade arquitetural**.

Verificadores comuns podem ser declarados uma vez na configuração do projeto:

```json
{
  "lean": {
    "architecture_sensors": ["npm run check:architecture"],
    "critical_paths": ["src/portfolio/valuation.ts", "src/settlement/*"]
  }
}
```

Adicione a seção sem substituir a configuração inteira. Padrões adicionais são
cumulativos; não removem as regras conservadoras de escalonamento. Uma exigência
arquitetural adicionada depois da preparação não é ignorada: requer replanejamento.

## Implementar e testar

Entregue o brief ao agente e permita que ele investigue, edite e teste dentro do
escopo. Não é necessário iniciar avaliadores a cada correção. O comando opcional
`check` executa apenas o menor tier de sensores disponível:

```powershell
python $RUNVERO --repo $APP check TASK-001
```

Se não houver `--quick-sensor`, o tier rápido usa o próximo tier disponível, que
pode ser o conjunto final. Nenhum handoff de revisão é criado por `check`.

O agente deve solicitar decisão antes de ampliar escopo, contrariar uma regra,
alterar permissões ou executar operações destrutivas. Esses limites não podem ser
substituídos por uma revisão posterior. Checkpoints do CLI legado continuam úteis
para interrupções e sessões longas, mas não são obrigatórios por edição.

## Verificar uma vez que a implementação esteja coerente

```powershell
python $RUNVERO --repo $APP verify TASK-001
```

`verify` executa os sensores finais e o scanner existente, rejeita mudanças de
código/contrato/configuração durante essa verificação e prepara:

```text
.harness/runs/<TASK>/<RUN>/lean/
  verification.json       Identidade do código, contrato, configuração e resultados
  review-request.json     Modelo de parecer; começa sem aprovação
  review-handoff.md       Instrução para revisão independente
```

A revisão deve usar uma sessão nova, sem herdar as conclusões do implementador.
Ela recebe acesso ao contrato, às regras na origem, ao diff completo desde o
início, aos arquivos novos e aos resultados. Não deve se limitar à lista de
caminhos sensíveis nem confiar somente no resumo do implementador.

O revisor copia `review-request.json` para `review.json` **dentro da pasta `lean/`**,
preenche sua identidade, decisão, evidência por critério, revisão arquitetural e
achados estruturados. `not_checked`, campos vazios e P0/P1 impedem o fechamento.
O código não produz pareceres aprovados automaticamente.

### Escalonamento

Use `prepare --risk critical` quando já souber que a mudança é sensível.
`verify` também eleva o risco por caminhos de autenticação, autorização,
pagamentos, migrations, infraestrutura, workflows, dependências e regras do
projeto. Os padrões são conservadores e **não analisam o significado do código**.
Uma única linha pode mudar uma permissão; o reviewer deve elevar `risk` para
`critical` quando encontrar esse risco ou quando houver dúvida relevante.

Nesse caso, obtenha também `evaluation.json` de outra sessão independente,
usando o mesmo formato, com `role: "evaluator"` e identidade diferente. Os dois
pareceres podem ser preparados em paralelo. Um resultado negativo de qualquer
um impede a aprovação.

### Revisão de linguagem sem aprovação fictícia

Mudanças em documentos, componentes de interface e catálogos de tradução exigem
revisão de linguagem registrada. Para outras mudanças, o revisor pode registrar
`ptbr.status: "not_applicable"` **com justificativa** quando nenhum texto relevante
mudou. Strings em backend também devem ser avaliadas pelo revisor: o filtro de
arquivos não detecta todas as linguagens ou situações.

A não aplicabilidade fica em `lean/applicability.json` e no orçamento da run;
não é fabricado um `ptbr-review.json` com `pass`. Uma revisão verdadeira é
registrada pelo comando legado com a identidade e a evidência fornecidas.

## Fechar

```powershell
python $RUNVERO --repo $APP finish TASK-001 `
  --review "$APP\.harness\runs\TASK-001\<RUN>\lean\review.json"
```

Para risco crítico, acrescente `--evaluation` apontando para o parecer do
avaliador. `finish` recusa identidade errada, parecer desatualizado, critérios
incompletos, evidência alterada e autor igual ao implementador. Depois aplica o
mesmo gate de conclusão do CLI existente, registra a avaliação e gera o relatório.
**Não cria PR, faz merge nem publica em produção.**

As identidades são declarações locais, não autenticação dos agentes nem prova
criptográfica de isolamento. Um usuário/agente com acesso de escrita a `.harness`
pode alterar seus arquivos; cabe ao operador garantir sessões independentes.
Os gates remotos e as aprovações de produção continuam necessários.

Orçamento de tempo e quantidade de tentativas são **informativos no fluxo normal**;
não reprovam uma entrega correta apenas por ter demorado. Para risco crítico,
o orçamento original é preservado e aplicado. Falhas no gate restauram os
metadados originais da run. Nenhuma configuração global é desativada.

As durações reais de cada comando são registradas no evento `lean_stage_completed`.
Incluem testes e observações síncronas; não representam tempo de inferência,
tokens, economia estimada ou acurácia do modelo. Use-as junto ao tempo das sessões
de implementação/revisão para comparar o fluxo antigo e o novo.

## JEV continua disponível

A integração permanece opt-in, em modo `shadow`, via Vercel AI Gateway. Ela nunca
aprova tarefas, executa correções, dispensa verificações ou concede permissões.
O gatilho padrão agora é **uma execução de sensores que falhou**, em vez de todo
resultado. Uma falha pode indicar ambiente; repetições distintas podem fornecer
sinais de ciclos improdutivos. As respostas continuam sendo hipóteses.

Depois de instalar o worker e revisar o preview conforme [JEV_OBSERVER.md](JEV_OBSERVER.md):

```json
{
  "jev_observer": {
    "enabled": true,
    "mode": "shadow",
    "allow_remote_state": true,
    "automatic_trigger": "failures",
    "timeout_seconds": 8,
    "min_interval_seconds": 15,
    "max_calls_per_run": 20
  }
}
```

`automatic_trigger` aceita `failures`, `manual` e `always`. `always` restaura o
acionamento em todo resultado booleano de sensores. Valores inválidos não
acionam a API. `preview`, `observe` e `status` manuais permanecem inalterados.
Em testes bem-sucedidos, o padrão não coleta contexto JEV, inicia Node nem gasta
chamadas. Em falhas, a chamada continua **síncrona e limitada por timeout**; não
há promessa de latência zero. Indisponibilidade preserva o resultado dos testes.

Nunca coloque a chave na configuração. A redação de segredos não elimina todo
risco de vazamento; reveja os dados que serão enviados e autorize por projeto.
Este PR não habilita envio remoto nem modifica credenciais dos projetos.

## Limites da primeira simplificação

Não é uma garantia universal de arquitetura, um novo orquestrador de modelos,
um sistema de isolamento de agentes ou uma medição de produtividade real. A
implementação reutiliza o CLI e o armazenamento existentes. Não muda fluxos
antigos em andamento nem remove o hub, Telegram, plugins ou retomada.

Para replanejar um contrato já iniciado, use explicitamente o fluxo completo;
o fluxo enxuto recusa aceitar um contrato modificado como se fosse o original.
Validação em navegador continua necessária quando a mudança pede isso; ela pode
ser executada por um script revisado ou por QA independente com evidência.
Não há integração automática nova com `browser-qa` nesta entrega.
