# JEV: observador de falhas, sem autonomia

A integração usa o JEV pelo Vercel AI Gateway para sugerir quando investigar
repetição de falhas ou problemas de ambiente. O agente continua implementando.
O Runvero continua controlando contratos, sensores e aprovações.

**Desativado por padrão. Somente modo `shadow`. Não aprova, pausa, retoma,
reinicia, instala, executa diagnósticos, escolhe modelos nem publica nada.**
Uma recomendação é uma hipótese para o operador, não um diagnóstico comprovado.

## O que está incluído

O resolvedor `harness_core/sensor_evidence.py` seleciona cronologicamente os
resultados elegíveis. Um `sensors-all.json` mais recente não pode ser ignorado
em favor de um `sensors-full.json` antigo. Não procura uma aprovação antiga para
substituir uma falha nova. Empates favorecem falha. Evidência ilegível ou com
identidade incompatível não produz aprovação.

O gate `final_sensor_payload()` usa esse resolvedor. Após os sensores, o mesmo
resolvedor atualiza o espelho `sensors.json`, consumido pelos briefs, relatórios
e dashboard existentes. Quando o contrato exige `full`, sensores rápidos são
apenas evidência preliminar: continuam visíveis no espelho, mas o resolvedor
final não os aceita. Os gates existentes de revisão, plano de comandos e hash
da superfície testada continuam obrigatórios e não dependem do JEV.

Após consentimento explícito, o gatilho automático padrão é uma invocação de
sensores que **falhou**. Resultados bem-sucedidos não coletam o estado do JEV,
não iniciam Node nem fazem chamadas ao provedor. Nas falhas elegíveis, a
observação continua síncrona, antes do retorno do comando, com os limites de
timeout, intervalo e orçamento existentes. Não monitora cada ferramenta interna
do Codex nem interrompe o agente. Checkpoints da mesma task/run fornecem histórico;
execuções rápidas no mesmo segundo podem sobrescrever checkpoints no formato
atual do Harness. O observador deduplica registros iguais e nunca deve tratar
duplicatas como prova de repetição.

As perguntas versionadas verificam possível repetição, possível bloqueio de
ambiente e insuficiência de evidência. As respostas são probabilidades booleanas,
não textos gerados. O Harness escolhe uma mensagem fixa em PT-BR. Não interpreta
um sinal fraco como confirmação de que o trabalho está correto.

## Instalação opcional

Execute a partir de um checkout do Runvero. O núcleo continua sem dependências
Python adicionais. Node.js 22+ e o SDK são necessários somente para chamadas
reais ao JEV. A integração usa um processo Node curto por observação; não é um
serviço residente nem uma medição da latência de inferência isolada.

```powershell
cd C:\caminho\runvero
npm install --prefix integrations/jev-worker --ignore-scripts --no-audit --no-fund
$env:AI_GATEWAY_API_KEY = "SUA_CHAVE_DO_GATEWAY"
```

O SDK `ai` está fixado em `7.0.105`, a versão mínima documentada com
`experimental_evaluate`. A instalação gera um lockfile local; dependências
transitivas ainda não estão travadas no repositório nesta entrega. O CI verifica
que essa versão expõe a função, sem chamar um modelo. Não coloque a chave no
repositório, em prompts, em contratos ou no arquivo de configuração do Harness.

Adicione a seção abaixo ao `.harness/config.json` **do projeto gerenciado**, sem
substituir as demais configurações. Os dois consentimentos precisam ser booleanos
JSON verdadeiros; strings como `"true"` não ativam a integração.

```json
{
  "jev_observer": {
    "enabled": true,
    "mode": "shadow",
    "allow_remote_state": true,
    "automatic_trigger": "failures",
    "timeout_seconds": 8,
    "min_interval_seconds": 15,
    "max_calls_per_run": 20,
    "signal_threshold": 0.85
  }
}
```

`automatic_trigger` pode ser `failures` (padrão), `manual` (sem chamadas
automáticas) ou `always` (todo resultado booleano de sensores). Para manter o
comportamento anterior de observar também os testes bem-sucedidos, configure
`always` explicitamente. Valores inválidos não acionam a API. Essa política é
compartilhada pelos comandos legados e pelo [fluxo enxuto](LEAN_WORKFLOW.md).
As ações manuais `preview`, `observe` e `status` não mudam por causa do gatilho.

Para desativar, remova a seção ou defina `enabled` como `false`. Nenhuma task muda
de status por isso. Sem Node, SDK, chave ou conectividade, a observação fica
indisponível; nenhuma regra de aprovação é relaxada.

## Inspecionar antes de enviar

```powershell
python -m harness_core.jev_observer --repo C:\projetos\app --task TASK-001 --action preview
```

`preview` é o padrão e não faz chamadas de rede. Mostra o estado limitado e
redigido e as perguntas. Verifique a adequação do conteúdo para envio ao provedor
antes de habilitar `allow_remote_state`.

Para uma observação manual ou leitura da última:

```powershell
python -m harness_core.jev_observer --repo C:\projetos\app --task TASK-001 --action observe
python -m harness_core.jev_observer --repo C:\projetos\app --task TASK-001 --action status
```

`--run NOME_DA_RUN` seleciona uma execução específica. Sem isso, usa a última
pasta de execução. O comando manual retorna código 2 para resultado indisponível
ou desatualizado. O callback automático não transforma isso em falha da task.
Após a ativação, os comandos legados `sensors`, `quick-pass` e `full-pass`, assim
como `check` e `verify` do fluxo enxuto, aproveitam o mesmo callback e o gatilho
configurado. A recomendação disponível aparece no terminal.

## Dados, privacidade e rastreabilidade

O estado contém objetivo, até seis critérios, evidência final e até quatro
amostras distintas de sensores da mesma execução, com até três resultados por
amostra. Saídas são limitadas e identificadas como parciais. Código-fonte inteiro,
histórico de conversa, arquivos de ambiente e variáveis de ambiente completas
não são enviados. Trechos de testes ainda podem conter código ou dados privados.

O transporte fica limitado a 32 KB de pedido e 16 KB de resposta. A redação
remove valores sensíveis conhecidos no ambiente, tokens comuns, credenciais em
URLs, cabeçalhos e chaves privadas, antes de truncar o texto. **Isso não é uma
solução completa de prevenção de vazamento**: dados comerciais, pessoais ou
segredos em formatos desconhecidos ainda podem estar nos logs. Autorize por
projeto e use fixtures/testes sem dados reais sempre que possível.

O pedido solicita `zeroDataRetention: true` no Gateway. Isso não substitui a
revisão dos termos, controles e logs da sua conta. Falhas de disponibilidade dessa
opção não causam fallback silencioso para uma requisição sem ela.

Arquivos ficam em `.harness/runs/<task>/<run>/jev/`:

- `observation-*.json`: estado redigido, hash, pedido reservado, resultado,
  probabilidades, tempo total e recomendação, quando disponível;
- `latest.json`: última observação. `status` verifica se ela ainda corresponde ao
  estado atual, em vez de mostrar recomendação velha como atual;
- `.observer.lock`: impede chamadas concorrentes na mesma run.

O registro nunca se chama `evaluation.json` e sempre tem `applied: false`.
Corpos de erros do SDK, cabeçalhos e respostas brutas não são persistidos.
Hashes cobrem contrato, run, payloads completos de sensores e superfície de
arquivos, inclusive mudanças não commitadas cobertas pelo hash atual do Harness.
Se isso mudar durante a chamada, a resposta é marcada `stale` e não vira conselho.
A política de limites não é uma estimativa de precisão: calibre o limiar com
exemplos reais, incluindo PT-BR, antes de ampliar o uso.

Tentativas malsucedidas também gastam o orçamento local. Há intervalo mínimo,
deduplicação de estados já observados e nenhum retry do SDK. Chamadas podem ser
repetidas após o intervalo quando o provedor esteve indisponível, respeitando o
limite da run. Os limites do Gateway devem complementar os limites locais.

Se o processo morrer abruptamente, a trava pode permanecer. Confirme que não há
observação ativa antes de remover **somente** `.observer.lock` dessa execução.
Não apague registros para contornar o orçamento. O log local não é um registro
criptograficamente protegido contra um usuário com acesso de escrita ao projeto.

## Validação e limites da entrega

```powershell
python -m pytest tests/test_jev_observer.py tests/test_lean_workflow.py -q
node --test integrations/jev-worker/worker.test.mjs
```

Testes usam um provedor simulado e não consomem API. Cobrem consentimento,
identidade de respostas, estado desatualizado, dados inválidos, segredos, timeout,
orçamento, concorrência, compatibilidade de evidências e preservação do estado
da task. Os testes do fluxo enxuto também cobrem o gatilho automático e a
preservação dos resultados quando o observador fica indisponível. Eles validam
a integração e as regras, **não a acurácia do JEV**.

Esta entrega não inclui roteamento de modelos, seleção semântica de memória,
triagem de diff, execução automática de diagnósticos nem integração com
`browser-qa`. Não reescreve históricos anteriores; rode novamente os sensores
finais em execuções antigas antes de usá-las como evidência de conclusão.

## Referências oficiais consultadas em 18/09/2026

- [Integração e versão mínima do SDK](https://vercel.com/changelog/typesafe-ai-jev-now-available-on-ai-gateway)
- [Modelo e contrato básico do Gateway](https://vercel.com/ai-gateway/models/jev)
