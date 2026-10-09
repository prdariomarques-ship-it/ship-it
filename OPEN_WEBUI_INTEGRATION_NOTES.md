# Integração Open WebUI ↔ Dario OS — Acompanhamento

> Documento vivo. Atualizado a cada decisão, teste ou bloqueio. Nada aqui é
> declaração de implantação — implantação só ocorre com janela aprovada e
> comprovação de rollback.

**Status geral:** 🔴 Fase de diagnóstico (somente leitura) — nenhuma edição
de produção feita.

**🚨 Bloqueio de segurança ativo:** a instalação Open WebUI da VPS roda com
`WEBUI_AUTH=False` (login desabilitado). Hoje isso não é um risco porque o
container só escuta em `127.0.0.1:3001` (não publicado externamente). **Não
posso criar uma rota pública/Caddy para esta instância enquanto
`WEBUI_AUTH=False`.** Habilitar autenticação é mudança de segurança —
precisa de aprovação específica antes de qualquer execução, por regra
explícita do usuário.

**Branch de trabalho:** `open-webui-integration` (criada a partir de `master`
em `/home/user/ship-it`).

---

## 1. Decisões tomadas

- Entrega separada da correção Flávio/Micael (incidente distinto, PR própria
  quando chegar a hora — "uma tarefa por incidente").
- Diagnóstico primeiro, somente leitura, antes de qualquer edição — igual ao
  protocolo já usado para `handlers.py`/`router.py`.
- Branch isolada a partir de `master`, sem merge amplo.

## 2. Divergências de base já identificadas

| Item | Repo (`master`) | Produção (informado/confirmado) | Status |
|---|---|---|---|
| Next.js (frontend) | `16.2.10` (`frontend/package.json`) | `16.3.6` (informado pelo usuário) | ⚠️ Divergente — confirmar via build real na VPS antes de editar `Sidebar.tsx` |
| `backend/jobs/handlers.py`, `backend/webhooks/router.py` | corrigido na PR #63 (commits `2ff7f4b`/`48061b0`) | — | ✅ Já resolvido (engajamento anterior) |
| `backend/agents/planner.py`, `backend/agents/store_agent.py`, `backend/services/descriptions.py`, `backend/orchestrator/context.py` | hashes locais não batem com produção (confirmado via `sha256sum` no container `darioos-evolution-backend-1`) | — | ⚠️ Pendente — incidente separado (Flávio/Micael), conteúdo real ainda sendo coletado |

## 3. Arquivos já localizados no repo (candidatos, ainda não confirmados contra produção)

- `frontend/components/Sidebar.tsx` — array `NAV_ITEMS`, estrutura simples
  (`{ href, label }` + `<Link>`). Adicionar "Central de IA" aqui é mudança
  estrutural pequena, mas só depois de confirmar que este arquivo é o que
  está realmente publicado.
- `frontend/components/admin/AdminSidebar.tsx` — sidebar separada da área
  admin, ainda não inspecionada em detalhe.

## 4. Diagnóstico pendente (somente leitura, via VPS)

- [ ] Confirmar roteamento real: domínio público → Caddy → frontend/backend → banco.
- [ ] Ler config **viva** do Caddy via admin API (`localhost:2019/config/`
    dentro do container) — **não presumir** que
  `/opt/chroma-migration-20260927/app.compose.prepared.json` continua igual.
- [x] Localizar instalação Open WebUI na VPS: imagem, versão, portas, volumes,
    rede, política de restart, healthcheck. — ver seção 2.1.
- [x] Verificar `WEBUI_AUTH` (= `False` ⚠️), `ENABLE_SIGNUP` (= `false`),
    presença (não valor) de `WEBUI_SECRET_KEY` e do arquivo
    `/app/backend/.webui_secret_key` (existe).
- [ ] Verificar memória disponível/pressão de swap na VPS (~6 GB RAM) antes de
    qualquer build ou serviço adicional.
- [ ] Entender o que é "FlowCore RAG" de fato (modelo/função/pipe/serviço
    externo). Não está nas variáveis de ambiente do container da VPS —
    provavelmente é config de aplicação (dentro do `webui.db`), só confirmado
    na instalação do PC até agora. Checar se existe também na instalação da
    VPS ou se é exclusivo do PC.
- [ ] Confirmar backups SQLite de 08/10 na VPS: versão, cobertura, local.
- [ ] Build real do frontend de produção — confirmar se usa mesmo `16.3.6` e
    se `Sidebar.tsx` publicado é igual ao do repo.

### 4.1 Achados confirmados (VPS, Open WebUI)

- Imagem: `ghcr.io/open-webui/open-webui@sha256:1a639...8b924` (fixada por
  digest). `WEBUI_BUILD_VERSION=0a7c15832fb30b1903753e83f81dc7d27e5b0944`.
- Volume nomeado `migrated-extras_open_webui` → `/app/backend/data` (não é
  volume anônimo — persiste entre recriações do container).
- Redes: `evolution` e `migrated-extras_default`. `darioos-evolution-caddy-1`
  também está na rede `evolution` — rota interna possível via
  `open-webui:8080`, sem depender de `127.0.0.1:3001`.
- `OLLAMA_BASE_URL=http://darioos-ollama-1:11434` — já aponta para o Ollama
  da própria VPS, não do PC. Bom sinal para independência do PC.
- `OPENAI_API_BASE_URL` vazio. `RAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`,
  `AUXILIARY_EMBEDDING_MODEL=TaylorAI/bge-micro-v2`, `RAG_RERANKING_MODEL`
  vazio. `USE_OLLAMA_DOCKER=false` (correto — usa o Ollama externo).

## 5. Testes executados

(nenhum ainda — fase de diagnóstico)

## 6. Bloqueios

- Sem acesso direto a shell da VPS nesta sessão — todo comando é relayed
  pelo usuário (copia/cola). Diagnóstico depende da disponibilidade dele
  para colar saídas.
- Hash de 4 arquivos de backend confirmados divergentes da produção
  (incidente Flávio/Micael) — conteúdo real ainda sendo coletado em paralelo.

## 7. Próximo passo

Diagnosticar o roteamento real (Caddy) e a instalação existente do Open WebUI
na VPS, com comandos somente leitura, um por vez.
