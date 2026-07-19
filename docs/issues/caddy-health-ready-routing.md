# Caddy não roteia `/health/ready` corretamente

**Status:** Aberta
**Versão alvo:** v1.4
**Prioridade:** P1
**Criada em:** 2026-07-19, durante o fechamento da Release 1.3.1

> Nota: criada como issue em markdown porque `gh auth status` não tem sessão
> autenticada neste ambiente (`gh auth login` necessário para abrir uma issue
> real no GitHub). Migrar para uma issue de verdade quando houver acesso.

## Problema

`GET /health/ready` — o endpoint de *readiness* que checa dependências reais
(Postgres, Redis, Qdrant, WhatsApp) — não é alcançável através do Caddy.

Confirmado ao vivo, 2026-07-19:

```
$ curl -s http://localhost/health/ready
(vazio)

$ curl -sv http://localhost/health/ready
< HTTP/1.1 308 Permanent Redirect
< Location: https://localhost/health/ready

$ curl -sk https://localhost/health/ready
<!DOCTYPE html>...<title>404: This page could not be found.</title>...
```

O endpoint funciona perfeitamente quando chamado direto no container,
ignorando o Caddy:

```
$ docker exec darioos-backend-1 python3 -c "..."
200 {"status":"ok","checks":{"database":"ok","redis":"ok","qdrant":"ok","whatsapp":"ok"}}
```

## Causa raiz

`docker/caddy/Caddyfile` só tem uma rota explícita para o path exato `/health`:

```
handle /health {
	reverse_proxy backend:8000
}
```

Não existe rota equivalente para `/health/ready`. Como esse path não casa com
nenhum `handle` explícito, ele cai no bloco genérico:

```
handle {
	reverse_proxy frontend:3000
}
```

— que encaminha para o Next.js, que por sua vez não tem uma rota
`/health/ready` e responde `404`.

Isso é anterior a qualquer mudança desta sessão — `/health/ready` nunca foi
alcançável de fora do container desde que o Caddyfile existe. Só foi
descoberto agora porque o runbook de rotação de credenciais do Postgres
pedia exatamente esse comando como passo de verificação.

## Impacto

- **Nenhum sistema interno depende disso hoje** — os `healthcheck` do
  próprio Docker Compose usam `pg_isready`/`wget` contra os containers
  diretamente, não passam pelo Caddy.
- **Ferramentas de observabilidade externas** (um uptime monitor, um load
  balancer de verdade, um runbook manual como o que motivou esta descoberta)
  que tentem checar o *readiness* real do sistema via HTTPS externo
  recebem um falso-negativo (`404`) em vez do status real — podem disparar
  alerta de "sistema fora do ar" quando na verdade está tudo saudável, ou
  pior, mascarar uma falha real de dependência (`checks.database: "erro"`)
  atrás de um 404 genérico do frontend.
- `/health` (sem o `/ready`) funciona normalmente — só o path mais
  detalhado é afetado.

## Correção sugerida

Adicionar uma rota explícita no Caddyfile, no mesmo bloco que já trata
`/health`:

```
handle /health {
	reverse_proxy backend:8000
}
handle /health/ready {
	reverse_proxy backend:8000
}
```

(Ou generalizar para `handle /health*` se qualquer sub-rota futura de health
também dever ir para o backend — decisão de escopo pra quem for implementar.)

## Critérios de aceite

- [ ] `curl -sk https://localhost/health/ready` retorna o JSON real do
      backend (`{"status":"ok","checks":{...}}`), não um 404 do Next.js.
- [ ] `curl -s http://localhost/health/ready` continua redirecionando pra
      HTTPS (comportamento correto e inalterado do Caddy) — mas o redirect
      deve resolver pro backend, não pro frontend.
- [ ] Teste de regressão (Playwright ou equivalente) cobrindo que
      `/health/ready` via Caddy retorna 200 com o shape esperado.
- [ ] `/health` (sem `/ready`) continua funcionando exatamente como hoje —
      não deve haver regressão nesse path.
