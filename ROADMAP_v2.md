# Roadmap v2 — Dario OS

Planejamento de versões futuras, a partir da v1.2.0. Este documento é
**planejamento, não implementação** — nenhum item aqui foi construído nesta
tarefa de consolidação pós-release. Prioridades e escopo exato de cada
versão podem mudar; o que não muda é a ordem de dependência entre elas
(confiabilidade de infraestrutura antes de autonomia de agente).

Para as limitações reais que motivam os itens de v1.3.0/v1.4.0, ver
`KNOWN_LIMITATIONS.md`. Para débito técnico geral, ver `TECHNICAL_DEBT.md`.

----------------------------------------

## v1.2.1 — Correções críticas apenas

Patch release, sem escopo funcional novo. Reservado exclusivamente para:

- Bugs de severidade alta descobertos em produção após a v1.2.0.
- Vulnerabilidades de segurança que exijam correção fora do ciclo normal.
- Nenhuma nova funcionalidade, nenhuma mudança de arquitetura.

----------------------------------------

## v1.3.0 — Confiabilidade de integrações externas

**Retry Google**

Os quatro domínios Google (Gmail, Calendar, Contacts, Drive) hoje não têm
retry/backoff configurável nas chamadas HTTP aos respectivos providers —
diferente do WhatsApp, que já tem
(`WHATSAPP_REQUEST_MAX_ATTEMPTS`/`WHATSAPP_REQUEST_BACKOFF_SECONDS`, ver
`providers/whatsapp/base.py`). Uma falha transitória de rede ou um erro
5xx passageiro da API do Google hoje propaga direto para o usuário em vez
de ser absorvido.

**Circuit Breaker**

Nenhum provider (Google, LLM, WhatsApp) tem circuit breaker — uma
integração externa degradada continua recebendo tráfego total em vez de
o sistema recuar automaticamente e tentar novamente depois de um
intervalo.

**Retry-After**

Nenhum provider respeita o header `Retry-After` de uma resposta 429 —
hoje, um rate limit do lado do Google/LLM/WhatsApp é tratado como um erro
genérico, sem usar a informação que o próprio serviço já devolve sobre
quando tentar de novo.

**Bulkhead**

Nenhum isolamento de recursos entre integrações — uma integração Google
lenta ou travada pode, em tese, consumir conexões/threads que outra
integração (WhatsApp, LLM) precisaria.

Escopo desta versão: fortalecer as integrações já existentes contra falhas
transitórias de rede. Não adiciona nenhum domínio novo, não muda contrato
de nenhuma API pública.

----------------------------------------

## v1.4.0 — Automação e operação assíncrona

**Scheduler**

Hoje não existe um agendador de tarefas recorrentes (ex.: "resumir a
agenda toda segunda de manhã", "reindexar uma pasta do Drive a cada 6h")
— tudo que roda hoje é disparado por evento (mensagem recebida) ou por
job pontual enfileirado explicitamente.

**Jobs** (evolução da fila existente)

A fila de jobs (Postgres, retry exponencial, claim atômico) já existe e é
usada em produção — esta versão amplia os tipos de job suportados e a
observabilidade por tipo de job, sem trocar a infraestrutura de fila em
si.

**Alertas**

Não existe hoje um canal de alerta proativo (ex.: notificar o operador
quando `/health/ready` fica `degraded` por mais que N minutos, ou quando
uma integração Google perde o refresh token) — a observação de saúde do
sistema hoje é inteiramente pull (`/health`, `/metrics`, dashboard admin).

**Fila** (visibilidade)

Expor a fila de jobs no Dashboard Administrativo com granularidade maior
(jobs pendentes por tipo, tempo médio de espera, taxa de retry) —
hoje o admin dashboard mostra execuções de agente, não o estado interno
da fila de jobs em si.

----------------------------------------

## v2.0.0 — Autonomia cognitiva

Mudança de escopo maior — candidata a `MAJOR` porque pode introduzir
comportamento novo de ponta a ponta (um agente agindo em múltiplas etapas
sem confirmação humana em cada uma), não apenas uma integração nova.

**Multi-Agent**

Hoje um plano do Cognitive Planner decompõe um pedido em até 5 etapas e
roteia cada etapa para *um* agente por vez, sequencialmente. Multi-Agent
significa agentes colaborando dentro do mesmo plano — um agente podendo
delegar/consultar outro diretamente, não apenas o Planner escolhendo qual
agente executa cada etapa isoladamente.

**Planning** (evolução)

O Cognitive Planner atual decompõe em até 5 etapas fixas e pede
confirmação humana conforme a heurística de risco. v2.0.0 avalia
planejamento mais profundo (mais etapas, replanejamento dinâmico quando
uma etapa falha).

**Autonomous Execution**

Hoje toda execução de agente acontece dentro do ciclo de uma única
mensagem/requisição. Execução autônoma significaria um agente operando ao
longo do tempo (ex.: "monitore esse e-mail e me avise quando responderem")
sem uma nova mensagem de entrada disparando cada passo — depende do
Scheduler (v1.4.0) como pré-requisito de infraestrutura.

**Self Healing**

Hoje uma falha (provider fora do ar, exceção não tratada) é registrada e
reportada, mas a recuperação é sempre manual ou por retry simples.
Self-healing significaria o sistema detectar um padrão de falha recorrente
e tomar uma ação corretiva automaticamente (ex.: trocar de provider LLM
permanentemente após N falhas consecutivas, não só um fallback pontual).

**Memory Evolution**

A memória hoje é armazenada e buscada, mas não é reorganizada/consolidada
automaticamente ao longo do tempo (ex.: mesclar memórias redundantes,
promover um padrão observado repetidamente a uma preferência estruturada
sem o usuário declarar isso explicitamente).

----------------------------------------

## Fora de qualquer versão planejada (não avaliado)

Itens levantados durante auditorias mas sem versão-alvo definida ainda —
ver `KNOWN_LIMITATIONS.md` e `TECHNICAL_DEBT.md` para a lista completa e
o racional de cada um (ex.: CSP/HSTS no Caddy, upgrade major do Next.js,
QR Code do WhatsApp no dashboard).
