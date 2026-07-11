# Sprint v1.2.1 — Plano

Este é um plano de **implementação futura** — nenhum item aqui foi
codificado durante esta tarefa de preparação. Baseado no backlog validado
em `SPRINT_v1.2.1_BACKLOG.md`.

## Objetivo

Corrigir as vulnerabilidades e bugs reais de severidade compatível com um
patch release, sem introduzir nenhuma funcionalidade, mudança de API,
mudança de banco, mudança de arquitetura ou mudança de regra de negócio —
exatamente como `ROADMAP_v2.md` já reserva v1.2.1: "correções críticas
apenas".

## Escopo

### Itens dentro da Sprint

1. **VULN-1 — CSP e HSTS no Caddyfile** (P1). Único item de complexidade
   real desta sprint. Ver estratégia de implementação abaixo.
2. **BUG-1 — Contagem de testes desatualizada no README** (P3, trivial).
   Incluído apenas se um PR de qualquer natureza já for tocar
   `README.md`; não justifica, sozinho, abrir um PR isolado.

### Itens fora da Sprint

Tudo listado em `SPRINT_v1.2.1_BACKLOG.md` sob "Fora do escopo v1.2.1":

- **VULN-2** (upgrade major do Next.js) — complexidade e superfície de
  regressão incompatíveis com um patch release; precisa de uma sprint
  própria com orçamento de regressão completo.
- Todas as 7 dívidas técnicas (retry Google, circuit breaker, backup do
  Qdrant, auditoria de execução, QR Code, Lighthouse, mypy) — sem
  mudança de comportamento urgente que justifique sair do ciclo normal;
  já roteadas para v1.3.0 ou sem versão-alvo.
- Todas as 8 melhorias arquiteturais — v1.4.0/v2.0.0 por definição, e
  proibidas nesta sprint por instrução explícita ("não alterar
  arquitetura").

## Estratégia de implementação

### VULN-1 — CSP/HSTS

Abordagem em duas etapas, para não repetir o motivo pelo qual isso não
foi feito na Sprint 5 (risco de quebrar a aplicação silenciosamente sem
poder testar contra HTTPS real):

1. **Etapa 1 — HSTS.** Baixo risco (`Strict-Transport-Security` não muda
   comportamento de carregamento de recursos, só força HTTPS em
   requisições futuras). Adicionar diretamente ao bloco `header {}` do
   Caddyfile.
2. **Etapa 2 — CSP em modo `Report-Only` primeiro.** Adicionar
   `Content-Security-Policy-Report-Only` (não `Content-Security-Policy`)
   apontando para um endpoint de coleta de violações (ou, na ausência de
   um, para logging local) em staging real por um período de observação
   antes de promover para a diretiva efetiva. Só promover para
   `Content-Security-Policy` real depois de confirmar, em staging com
   HTTPS real, que nenhuma violação inesperada foi reportada durante o
   uso normal da aplicação (login, dashboard principal, dashboard admin,
   todas as integrações Google, envio/recebimento de WhatsApp).
3. Política inicial recomendada (ponto de partida, a refinar durante o
   período de observação): `default-src 'self'; script-src 'self';
   style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src
   'self'` — `'unsafe-inline'` em `style-src` porque não há evidência,
   nesta auditoria, de que os estilos inline do Next.js/Tailwind foram
   auditados para remoção segura; refinar isso é trabalho de uma sprint
   futura, não desta.

### BUG-1 — README

Correção de uma linha (`README.md:103`, `473 testes pytest` →
`555 testes pytest`), sem revisão adicional necessária.

## Estratégia de rollback

- **HSTS**: reversível instantaneamente removendo a linha do Caddyfile e
  reiniciando o container `caddy` — navegadores que já cachearam o header
  HSTS continuam forçando HTTPS pelo `max-age` configurado, mas isso não
  quebra nada (o domínio já serve HTTPS via Caddy automaticamente).
- **CSP** (`Report-Only`): rollback trivial — remover o header não afeta
  nenhum comportamento em produção, já que modo `Report-Only` nunca
  bloqueia nada.
- **CSP** (efetiva, depois de promovida): rollback = reverter o commit /
  remover o header do Caddyfile e reiniciar o container. Como é uma
  mudança de configuração de borda (Caddy), não de código da aplicação,
  o rollback não exige rebuild de backend/frontend nem migração de banco.
- **BUG-1**: rollback trivial (reverter uma linha de comentário).

Nenhum item desta sprint tem estado persistente (banco, fila, cache)
envolvido — todo rollback é reversão de configuração ou texto, sem
necessidade de migração de dados.

## Plano de testes

- **VULN-1 (HSTS)**: smoke test manual — confirmar que o header
  `Strict-Transport-Security` aparece na resposta (`curl -I`) depois do
  deploy em staging.
- **VULN-1 (CSP, fase Report-Only)**: rodar a suíte E2E completa
  (Playwright, 23 testes) contra o ambiente com o header ativo — nenhum
  teste deve reportar um recurso bloqueado (os testes já verificam
  ausência de erros de console em `performance.spec.ts`, que capturaria
  uma violação de CSP se o navegador a reportasse como erro). Revisar
  manualmente os relatórios de violação acumulados no período de
  observação antes de promover para efetiva.
- **VULN-1 (CSP, fase efetiva)**: repetir a suíte E2E completa com a CSP
  já em modo efetivo (não mais `Report-Only`) antes de promover a
  produção — se algum teste falhar por um recurso bloqueado, a política
  precisa de ajuste antes do deploy, não depois.
- **BUG-1**: nenhum teste automatizado aplicável (mudança de comentário);
  revisão visual do diff é suficiente.
- **Regressão geral obrigatória antes de qualquer merge desta sprint**:
  `ruff check .`, `pytest`, `npx tsc --noEmit`, `npx eslint . --ext
  .ts,.tsx`, `npm test`, `npm run e2e`, `npm run build`, `docker compose
  config` — os mesmos comandos já usados em toda sprint anterior deste
  projeto (ver `CONTRIBUTING.md`).

## Critérios de aceite

1. `Strict-Transport-Security` presente em toda resposta HTTP servida
   pelo Caddy em staging, com `max-age` de no mínimo 6 meses.
2. `Content-Security-Policy` (não mais `Report-Only`) presente em toda
   resposta HTML, sem nenhuma violação registrada durante um período de
   observação em staging cobrindo: login, dashboard principal (todas as
   10 páginas), dashboard admin (todas as 12 páginas), e pelo menos um
   fluxo completo de cada integração Google conectada.
3. Suíte completa passando: Pytest (555+), Vitest (108+), Playwright
   (23+), TypeScript, ESLint, Ruff, build de produção, `docker compose
   config` — todos verdes, sem exceção.
4. `README.md:103` consistente com `README.md:317` (mesma contagem de
   testes nos dois lugares).
5. `git status` limpo antes de qualquer merge — nada fora do escopo desta
   sprint incluído no PR.
6. Nenhuma API pública, contrato de banco, Provider, Agent, Orchestrator,
   Event Bus, OAuth ou regra de negócio alterada — confirmado por
   revisão de diff antes do merge (o diff inteiro deve tocar apenas
   `docker/caddy/Caddyfile` e, opcionalmente, uma linha de `README.md`).
