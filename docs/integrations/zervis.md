# Integração Dario OS ↔ Zérvis

O [Zérvis](https://github.com/gestordescomplicaa-web/zervis) (assistente de voz
e orquestrador de sessões de código, AGPL-3.0) lê o estado do Dario OS por uma
**ponte** em processo separado (`integrations/zervis/`). A fronteira é de rede:
nenhum código do Zérvis entra neste repositório, nem o contrário.

```
Zérvis ──MCP/HTTP (Bearer A)──▶ zervis-bridge ──GET (Bearer B, escopo darioos:read)──▶ backend /api
                                      ▲
                                      └── Redis pub/sub `darioos:events` (sanitizado)
```

- **Bearer A** (`ZERVIS_BRIDGE_MCP_TOKEN`): quem fala com a ponte. Aleatório, gerado por você.
- **Bearer B** (`ZERVIS_BRIDGE_DARIOOS_TOKEN`): token com escopo de leitura
  (ADR-0003). A ponte nunca devolve B ao Zérvis.

## Garantias

- **Só leitura.** O cliente HTTP da ponte só tem `GET`; o token só alcança o
  allowlist de `auth/scopes.py`. Escrita (ex.: `POST /agents/{name}/run`) é
  outra fase, com ADR própria e aprovação falada.
- **Eventos: deny by default** (`zervis_bridge/sanitize.py`). Só passam eventos
  listados, com campos listados. Nunca saem `phone`, `contact_id`, `user_id`,
  `job_payload`, conteúdo de mensagem nem `admin.*` (carrega valores de
  configuração). Strings são cortadas em 200 caracteres.
- **Autenticação** Bearer em tempo constante, proteção a DNS rebinding
  (`ZERVIS_BRIDGE_ALLOWED_HOSTS`), `/healthz` público sem dados.
- **Falha fechado.** A ponte não inicia sem os dois segredos (mín. 16 caracteres).
- **Eventos são best-effort** (o bus não persiste). `darioos_recent_events`
  devolve `gap: true` quando eventos se perderam entre duas consultas.

## Ferramentas MCP

| Ferramenta | Fonte |
|---|---|
| `darioos_status` | `/admin/status` + saúde da ponte |
| `darioos_agents` | `/admin/agents` |
| `darioos_executions` | `/admin/executions` (`period`, `agent`, `limit`) |
| `darioos_context` | `/admin/observation` |
| `darioos_goals`, `darioos_goals_ready` | `/goals`, `/goals/ready` |
| `darioos_tasks` | `/tasks` |
| `darioos_recent_events` | buffer de eventos (`since`, `limit`) |

## Subir (primeiro local, depois VPS)

1. Token do Dario OS, dentro do container do backend:
   `python scripts/mint_scoped_token.py --email <dono> --days 30`
2. Em `docker/.env`: `ZERVIS_BRIDGE_DARIOOS_TOKEN=<token acima>` e
   `ZERVIS_BRIDGE_MCP_TOKEN=$(openssl rand -hex 32)`.
3. `docker compose -f docker/docker-compose.yml --profile zervis up -d --build zervis-bridge`
   (opt-in; publica só em `127.0.0.1:8810`). Teste: `curl localhost:8810/healthz`.
4. Revogar tudo: `SCOPED_TOKEN_REVOKED_BEFORE=<unix agora>` no backend e reiniciar.

## Registro no Zérvis

Formato do `~/.config/zervis/mcp.toml` conferido no commit `a38b75d` do
Zérvis (`jarvis/cerebro/mcp_externo.py`); fixe a versão, o projeto ainda não
tem release. O Zérvis só aceita `http` em https ou loopback: use a ponte na
mesma máquina, ou um túnel/proxy TLS, nunca `http` aberto na rede.

```toml
[servidores.darioos]
tipo = "http"
url = "http://127.0.0.1:8810/mcp"
cabecalhos = { Authorization = "DARIOOS_BRIDGE_AUTH" }  # variável com o valor "Bearer <token A>"
livres = [
  "darioos_status", "darioos_agents", "darioos_executions", "darioos_context",
  "darioos_goals", "darioos_goals_ready", "darioos_tasks", "darioos_recent_events",
]
```

`DARIOOS_BRIDGE_AUTH` entra no ambiente do serviço do Zérvis (ou como segredo
pelo painel), com o valor `Bearer <ZERVIS_BRIDGE_MCP_TOKEN>`. As ferramentas
aparecem para o cérebro como `mcp__darioos__darioos_*`. Todas são somente
leitura, por isso `livres`; qualquer ferramenta de escrita futura **não** deve
entrar nessa lista.

## Risco residual

O que o token lê (metas, tarefas, agenda, execuções) chega ao Zérvis e, via
cérebro, ao provedor de LLM configurado lá. Cada ferramenta nova é uma decisão
de privacidade, não um detalhe.
