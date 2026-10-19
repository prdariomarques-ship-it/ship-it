# Árvore do Codex (frontend em execução em localhost:3000) - estado e protocolo de integração

Registrado em 2026-10-19, somente leitura. Nada nesta árvore foi alterado, limpo ou descartado.

## 1. Estado real

| Item | Valor |
|---|---|
| Caminho | `C:\Users\dario\Documents\Codex\2026-09-16\files-pasted-by-the-user-agentes\work\ship-it` |
| Branch @ commit | `codex/marquescolor-evolution` @ `f6084dfaa175784683addc2e1d0430502af11672` |
| Alterações locais | 80 entradas no `git status --porcelain`: 40 arquivos rastreados modificados + 40 arquivos novos (untracked) |
| Natureza | **Não é só frontend.** Inclui backend (`webhooks/router.py`, `jobs/handlers.py`, `agents/darius_twin.py`, `orchestrator/twin_risk_gate.py`, `providers/whatsapp/*`, `models/message.py`, PDV/`store_pos`, STT, migrações Alembic novas `7d31a9b4e2c1` e `9e2f1c6d7a80`), Docker (`docker/local-control/`, `docker/speech/`) e ~16 arquivos de frontend (`tarefas`, `loja`, `conversas`, `admin/whatsapp`, `admin/google`, `ResourceTable`, `Sidebar`, `useApi`, `ProductsPanel`, `POSPanel`, `ListPagination`, `usePaginatedApi`, testes) |
| Backups `.bak-dual-instance` | 5 arquivos (`jobs/handlers.py`, `models/message.py`, `repositories/message.py`, `services/messaging.py`, `webhooks/router.py`) + `patch_dual_instance.py`: trabalho de "instância dupla" **em andamento** |
| Relação com o repo alvo | clone **separado**: o commit `e64d2f7` (base da minha branch) não existe nele. Arquivos alterados nos dois lados: `backend/main.py` e `backend/utils/config.py` |
| Fins de linha | muitos arquivos do working copy estão em CRLF; um `git diff` completo gera ruído (patch de ~194 mil linhas). Alterações reais por `--numstat`: baixo volume (ex.: `tarefas/page.tsx` +29/-2) |

## 2. Como o `localhost:3000` é servido

- `darioos-local-control-control-1` (Caddy, `127.0.0.1:3000->80`) monta **por bind** `docker/local-control/Caddyfile` e `public/` desta árvore. Apagar ou mover esses arquivos quebra o :3000.
- `darioos-local-control-frontend-1` roda a **imagem já construída** `darioos-migrated-frontend:pdv-20260927` (build com `NEXT_PUBLIC_API_URL=/api`). Editar o código da árvore **não** altera a tela até alguém reconstruir a imagem.
- Roteamento do Caddy: `/api/*`, `/health*` -> `https://admissaoazusa.com.br` (**backend de produção no VPS**); `/manager`, `/assets`, `/evolution-api` -> o mesmo host; tudo mais -> `frontend:3000`.
- Consequência: o :3000 hoje conversa com a **produção**, não com um backend local. As rotas `/api/admin/darius/*` desta integração **não existem lá** e só passariam a existir após um deploy (não autorizado).

## 3. Snapshot de proteção (fora da árvore e fora do repo)

`C:\Users\dario\backups\codex-ship-it-20261019\`: `tracked-changes.patch` (`git diff --binary`, SHA-256 `0F78A0FF5D2B27F6840A9B6943C34EFA353B2E859FDEC2DE6AB04E160F8DFCEB`), `untracked/` (40 de 40 arquivos novos copiados), `untracked-files.txt`, `HEAD.txt`. Verificado que o `git status` da árvore ficou idêntico antes e depois.

## 4. Protocolo de integração segura (decisão)

1. **Nunca** editar, limpar, trocar de branch, reconstruir imagem nem reiniciar containers desta árvore sem autorização. Ela é a fonte do trabalho de "instância dupla"/PDV do Codex.
2. Telas novas do painel DARIUS são **arquivos novos** na branch `integration/dario-os-darius` (`frontend/app/admin/darius/*`, `frontend/lib/darius-types.ts`, `frontend/components/darius/*`), sem tocar nos ~16 arquivos de frontend alterados pelo Codex. Única costura: um item de menu em `Sidebar.tsx` (1 linha) e tipos em `admin-types.ts`, a reconciliar via diff no momento da mescla.
3. Desenvolvimento e testes do painel contra o **backend local** desta branch (porta própria), nunca contra o :3000/produção.
4. Mescla futura: quando o usuário autorizar, o trabalho do Codex é commitado na própria branch dele (ou aplicado como patch sobre a minha) com **diff revisado arquivo a arquivo**, resolvendo `main.py`/`config.py`. Só então reconstruir a imagem do frontend.
5. Qualquer deploy/rebuild/restart continua dependendo de autorização explícita.
