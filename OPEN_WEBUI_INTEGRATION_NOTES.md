# Integração Open WebUI ↔ Dario OS — Acompanhamento

> Documento vivo. Atualizado a cada decisão, teste ou bloqueio. Nada aqui é
> declaração de implantação — implantação só ocorre com janela aprovada e
> comprovação de rollback.

**Status geral:** 🔴 Fase de diagnóstico (somente leitura) — nenhuma edição
de produção feita.

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
- [ ] Ler config atual do Caddy (labels, roteamento) — **não presumir** que
  `/opt/chroma-migration-20260927/app.compose.prepared.json` continua igual.
- [ ] Localizar instalação Open WebUI na VPS: imagem, versão, portas, volumes,
    rede, política de restart, healthcheck.
- [ ] Verificar `WEBUI_AUTH`, presença (não valor) de `WEBUI_SECRET_KEY` e do
    arquivo `/app/backend/.webui_secret_key`.
- [ ] Verificar memória disponível/pressão de swap na VPS (~6 GB RAM) antes de
    qualquer build ou serviço adicional.
- [ ] Entender o que é "FlowCore RAG" de fato (modelo/função/pipe/serviço
    externo) e suas dependências do PC Windows (Ollama, arquivos, embeddings).
- [ ] Confirmar backups SQLite de 08/10 na VPS: versão, cobertura, local.
- [ ] Build real do frontend de produção — confirmar se usa mesmo `16.3.6` e
    se `Sidebar.tsx` publicado é igual ao do repo.

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
