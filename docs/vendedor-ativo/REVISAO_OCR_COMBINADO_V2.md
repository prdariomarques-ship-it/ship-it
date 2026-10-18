# Revisão do pacote `dario-ocr-combined-v2-review` (18/10/2026)

ZIP recebido: sha256 `0ba5ff41eba09c6a21367461c9a2815d1d87fc7cd5f0e9a5349734afed14ad9b`. Extraído em pasta isolada; nada executado do pacote, nada aplicado na VPS.

## Frontend — reproduzido
- `frontend/changes.patch` aplica limpo na árvore do repositório (`git apply --check`), pois os arquivos batem com `original_sha256` do manifesto.
- Em cópia descartável: **368 testes / 52 arquivos passaram**, `tsc --noEmit` sem erros, ESLint nos fontes alterados com 0 erros (os arquivos de teste são ignorados pela configuração de lint).
- O botão chama só `/chat/ocr`, com `expected_instance`, `AbortController` e checagem de troca de sessão. Nenhum `dangerouslySetInnerHTML`.
- Não verificado: build de produção, navegador real, Docker.

## Backend — NÃO verificável a partir deste repositório
- O repositório **não tem OCR**: sem coluna `ocr_text`/`ocr_provenance`, sem migration, sem extração. A base do patch é a árvore enviada pelo usuário (OCR v16, terminações CRLF), que inclui até `tests/test_ocr_evolution_timeline.py`, ausente aqui.
- 4 dos 6 arquivos existentes (`chat/router.py`, `chat/schemas.py`, `chat/service.py`, `api/schemas.py`) diferem do repositório **só por CRLF**. `api/routes.py` e `api/contact_workspace.py` diferem no conteúdo (o contexto do patch assume campos OCR que o repositório não tem).
- Portanto os 43 testes de backend do pacote **não foram reproduzidos**; a revisão do backend foi só de leitura.
- APIs que o código usa existem no repositório com a assinatura esperada: `UserRepository.get_first_admin`, `MessageRepository.get`, `agent_run_timeout_seconds`, `LLMResult.tool_calls`, `MessageMediaType` com valores minúsculos.

## Pontos de atenção
1. **`ChatRequest` ganhou `extra="forbid"`**: qualquer cliente que hoje mande campo extra para `/api/chat` passa a receber 422. O frontend deste repositório não chama `/chat`; é preciso conferir outros clientes antes de aplicar.
2. **Ruído de fim de linha**: `chat/*` aparece reescrito por inteiro (CRLF→LF). Em `api/routes.py` (15 linhas) e `api/contact_workspace.py` (3 linhas) o candidato mistura LF e CRLF. Só whitespace, mas dificulta revisar e aplicar.
3. Inconsistência de números no próprio pacote: o README cita 362 testes de frontend e 41 de backend; `summary.json` e o checklist citam 368 e 43. Reproduzi 368.
4. A explicação envia o OCR e a legenda ao provedor de IA configurado (há aviso antes do clique). Anexos enviados pelo próprio dono (`fromMe`) ficam fora, por desenho.
5. Rollback do backend antigo reabre a exposição de OCR no workspace para usuários não proprietários (o próprio checklist avisa).

## Relação com o owner-guard
Nenhum arquivo em comum (OCR: `chat/`, `api/`; guard: `handlers.py` de produção, `owner_activity`, `line_watch`). São independentes, mas ambos mexem em produção: aplicar um de cada vez, o guard primeiro (menor, com rollback e harness).

## Recomendação
Não aplicar o OCR ainda. Antes: identificar o backend realmente em execução (digest da imagem v16), repetir lá os 43 testes e tratar o item 1.
