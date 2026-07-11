# Sprint v1.2.1 — Backlog Oficial

Backlog gerado a partir de verificação direta no código da branch `master`
(commit `d2ffc8a`), não da documentação — cada item foi confirmado ou
descartado lendo o arquivo real. Ver `SPRINT_v1.2.1_PREPARATION_REPORT.md`
para a tabela completa de validação de P0s (arquivo/função/linha).

Nenhum item marcado **JÁ CORRIGIDO** entra neste backlog — backlog é
trabalho futuro, não histórico. A tabela de validação completa (incluindo
os 5 itens já corrigidos na v1.2.0, reverificados aqui) está no relatório
de preparação.

Todo item abaixo está etiquetado com **Dentro do escopo v1.2.1** ou **Fora
do escopo v1.2.1** — `ROADMAP_v2.md` já reserva v1.2.1 exclusivamente para
"correções críticas apenas" (bugs de severidade alta e vulnerabilidades de
segurança). Itens de confiabilidade/arquitetura já têm versão-alvo própria
e permanecem lá.

----------------------------------------

## BUGS

### BUG-1 — Contagem de testes desatualizada dentro da árvore de diretórios do README

- **Descrição**: `README.md:103` (dentro do diagrama ASCII da árvore de
  `backend/`) mostra `tests/  # 473 testes pytest`, enquanto
  `README.md:317` (seção "Desenvolvimento") mostra corretamente
  `# Testes backend (555 testes; cobertura ~94%)`. O número real,
  reconfirmado nesta auditoria (`pytest -q`), é 555. As duas linhas do
  mesmo arquivo se contradizem.
- **Prioridade**: P3 (cosmético — não afeta comportamento, só a precisão
  de um comentário dentro de um bloco de código ilustrativo)
- **Impacto**: Nenhum em produção; confunde um novo colaborador lendo o
  README pela primeira vez.
- **Complexidade**: Trivial (uma linha).
- **Estimativa**: 5 minutos.
- **Dependências**: Nenhuma.
- **Risco**: Nenhum — mudança de comentário/texto, sem código.
- **Escopo v1.2.1**: Dentro do escopo (é uma correção, não uma
  funcionalidade nova) — mas de prioridade tão baixa que pode ficar para
  o primeiro PR de qualquer natureza que já toque `README.md`, em vez de
  justificar um PR isolado.

Nenhum outro bug em aberto foi encontrado. Os 5 bugs reais documentados em
`SPRINT5_REPORT.md`/`CHANGELOG.md` (busca semântica do Qdrant quebrada,
erro de login não exibido, favicon ausente, 3 violações de contraste + 1
gap de foco por teclado, overflow mobile) foram reverificados linha a
linha nesta auditoria e confirmados **JÁ CORRIGIDOS** na v1.2.0 — ver
`SPRINT_v1.2.1_PREPARATION_REPORT.md`.

----------------------------------------

## VULNERABILIDADES

### VULN-1 — CSP e HSTS ausentes no Caddyfile

- **Descrição**: `docker/caddy/Caddyfile`, bloco `header {}` (linhas
  5–10), define `X-Content-Type-Options`, `X-Frame-Options` e
  `Referrer-Policy`, mas nenhuma `Content-Security-Policy` nem
  `Strict-Transport-Security`. Um XSS bem-sucedido em qualquer página do
  frontend não tem uma segunda camada de contenção (CSP), e conexões HTTP
  não são automaticamente promovidas a HTTPS em requisições subsequentes
  (HSTS).
- **Prioridade**: P1
- **Impacto**: Médio — não é explorável sozinho (não é uma vulnerabilidade
  ativa, é a ausência de uma mitigação em profundidade), mas amplia o
  raio de dano de qualquer XSS futuro e permite downgrade para HTTP em
  redes hostis (Wi-Fi público, etc.) até o primeiro redirect.
- **Complexidade**: Média — o próprio `TECHNICAL_DEBT.md`/`SECURITY_AUDIT.md`
  já registram por que isso não foi feito na Sprint 5: uma CSP mal
  calibrada pode quebrar carregamento de scripts/estilos/fontes em
  produção, e não há como testar isso contra HTTPS real e os domínios de
  asset reais dentro de um sandbox de desenvolvimento. Precisa de um
  ambiente de staging real com HTTPS para validar antes de aplicar em
  produção.
- **Estimativa**: 0.5–1 dia de implementação + validação em staging real
  (não em sandbox) antes de promover a produção.
- **Dependências**: Acesso a um ambiente de staging com HTTPS real
  (domínio + Let's Encrypt funcionando) para validar a CSP sem quebrar a
  aplicação silenciosamente.
- **Risco**: Médio-alto **se aplicado sem validação em staging real** — uma
  CSP restritiva demais pode quebrar a aplicação inteira em produção sem
  aviso (scripts/estilos bloqueados silenciosamente pelo navegador). Baixo
  risco se seguir a recomendação já registrada: começar com
  `Content-Security-Policy-Report-Only` antes de aplicar de verdade.
- **Escopo v1.2.1**: Dentro do escopo — é uma vulnerabilidade de segurança
  que `ROADMAP_v2.md` já lista como critério de entrada para v1.2.1
  ("vulnerabilidades de segurança que exijam correção fora do ciclo
  normal"). Recomenda-se, porém, tratar como o item de maior risco de
  regressão desta sprint — ver estratégia de rollback em
  `SPRINT_v1.2.1_PLAN.md`.

### VULN-2 — CVEs conhecidas em `next@14.2.21` e `postcss`

- **Descrição**: `frontend/package.json:29` fixa `"next": "14.2.21"`.
  `npm audit` (reexecutado nesta auditoria) reporta 1 CVE crítica e várias
  altas na cadeia do Next.js (exposição de informação no dev server sem
  verificação de origem, SSRF via middleware, DoS via Server Components,
  cache poisoning, XSS em scripts `beforeInteractive`, entre outras — ver
  lista completa em `SECURITY_AUDIT.md`) e uma CVE moderada em `postcss`
  (XSS via stringify de CSS não escapado).
- **Prioridade**: P2
- **Impacto**: Médio — a maioria dos CVEs listados afeta cenários
  específicos (dev server exposto publicamente, middleware customizado
  usando redirect de forma insegura, i18n do Pages Router — o projeto usa
  App Router) que não necessariamente se aplicam à configuração real de
  produção deste projeto, mas não há garantia disso sem uma auditoria CVE
  por CVE contra a configuração exata em uso.
- **Complexidade**: Alta — a correção via `npm audit fix --force`
  instalaria `next@16.2.10` e `eslint-config-next@16.2.10`, um upgrade
  *major* (App Router mudou entre Next 14 e 16; risco real de breaking
  changes em rotas, middleware, ou build).
- **Estimativa**: 3–5 dias (upgrade + regressão completa de todas as 23
  páginas + suíte E2E Playwright + build de produção), fora do
  orçamento de um patch release.
- **Dependências**: Nenhuma técnica, mas exige uma sprint dedicada com
  orçamento de regressão completo — não cabe como "correção crítica"
  pontual.
- **Risco**: Alto se feito às pressas dentro de um patch release — upgrade
  major de framework é exatamente o tipo de mudança que `ROADMAP_v2.md`
  reserva para uma versão própria, não para v1.2.1.
- **Escopo v1.2.1**: **Fora do escopo.** Recomendação: avaliar CVE a CVE
  contra a configuração real de produção (quantas se aplicam de fato) como
  uma tarefa de análise de risco isolada e barata, e só then decidir se o
  upgrade major vira uma versão própria no roadmap ou se mitigações
  pontuais (ex.: garantir que o dev server nunca é exposto publicamente)
  já reduzem o risco residual a um nível aceitável sem o upgrade.

----------------------------------------

## DÍVIDAS TÉCNICAS

Todos os itens abaixo foram reconfirmados diretamente no código nesta
auditoria. Nenhum é um bug — são gaps de capacidade aceitos por decisão
de escopo em sprints anteriores, com versão-alvo já definida em
`ROADMAP_v2.md`. **Nenhum entra no escopo de v1.2.1.**

| Item | Onde confirmado | Versão-alvo |
|---|---|---|
| Sem retry/backoff nos 4 providers Google (Gmail/Calendar/Contacts/Drive) | `providers/mail/gmail/provider.py`, `providers/calendar/google/provider.py`, `providers/contacts/google/provider.py`, `providers/drive/google/provider.py` — zero ocorrências de retry/backoff, diferente de `providers/whatsapp/base.py:143-153` | v1.3.0 |
| Sem circuit breaker / `Retry-After` / bulkhead em nenhum provider | Mesma verificação acima | v1.3.0 |
| Backup do Qdrant não automatizado | `scripts/backup.sh` — só `pg_dump` do Postgres | Não planejado |
| Sem tabela de auditoria de execução por agente/tool | `admin/router.py:305-315` (`admin_executions`, docstring confirma explicitamente) | Não planejado |
| QR Code do WhatsApp não exposto no dashboard | Nenhuma ocorrência de `qr_code`/`get_qr`/`qrcode` em `providers/whatsapp/` | Não planejado |
| Lighthouse nunca executado | Confirmado em `PERFORMANCE_REPORT.md`, sem contradição encontrada no código/CI | Não planejado |
| `mypy` não configurado | Nenhum `mypy.ini`/`[tool.mypy]` em `backend/` | Não planejado |

----------------------------------------

## MELHORIAS ARQUITETURAIS

Todos fora do escopo de v1.2.1 por definição — mudanças de arquitetura são
explicitamente proibidas nesta sprint de preparação e nas sprints de
correção crítica em geral. Já roteadas em `ROADMAP_v2.md`.

| Item | Versão-alvo |
|---|---|
| Scheduler de tarefas recorrentes | v1.4.0 |
| Alertas proativos de saúde do sistema | v1.4.0 |
| Visibilidade granular da fila de jobs no dashboard admin | v1.4.0 |
| Multi-Agent (colaboração entre agentes dentro de um plano) | v2.0.0 |
| Planning mais profundo / replanejamento dinâmico | v2.0.0 |
| Autonomous Execution | v2.0.0 |
| Self Healing | v2.0.0 |
| Memory Evolution | v2.0.0 |

----------------------------------------

## Resumo

| Grupo | Itens no escopo v1.2.1 | Itens fora do escopo |
|---|---|---|
| Bugs | 1 (P3, trivial) | 0 |
| Vulnerabilidades | 1 (VULN-1, CSP/HSTS) | 1 (VULN-2, upgrade Next.js) |
| Dívidas técnicas | 0 | 7 |
| Melhorias arquiteturais | 0 | 8 |

**O backlog real de v1.2.1 é pequeno por construção**: nenhum bug de
severidade alta está em aberto na branch `master` hoje (todos os 5
conhecidos já foram corrigidos na v1.2.0), e das duas vulnerabilidades
reais encontradas, só uma (CSP/HSTS) tem complexidade compatível com um
patch release. Isso é consistente com `ROADMAP_v2.md`, que já descreve
v1.2.1 como reservado "exclusivamente" para esse tipo de item — não é
esperado que todo patch release tenha um backlog volumoso.
