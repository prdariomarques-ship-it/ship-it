# Ajuste ao pacote OCR v2 — item 1 (`extra="forbid"` em `ChatRequest`)

**Problema:** o candidato pôs `extra="forbid"` em todo o `ChatRequest`. Qualquer cliente que hoje mande um campo a mais para `/api/chat` passaria a receber 422.

**Ajuste:** `ChatRequest` volta a ignorar campos desconhecidos (contrato antigo) e recusa com 422, antes de qualquer agente, apenas `ocr_source_message_id` e `expected_instance`, que só existem em `/chat/ocr`. A garantia do checklist ("payload OCR enviado por engano ao `/api/chat` → 422") continua valendo. `OCRChatRequest` mantém `extra="forbid"`.

- `schemas.py` — `chat/schemas.py` corrigido (parte do candidato do pacote v2, em LF).
- `schemas.py.diff` — diferença contra o candidato.
- `test_chat_request_compat.py` — 4 testes. Passam com o ajuste; com o arquivo original do candidato, 3 dos 4 falham (o cliente legado é recusado e a mensagem 422 não aponta `/chat/ocr`).

**Não aplicado em lugar nenhum.** Vale só como substituto de `chat/schemas.py` do pacote OCR v2; o resto do pacote continua não verificado contra o backend de produção (ver `../REVISAO_OCR_COMBINADO_V2.md`). Atenção ao fim de linha: o original enviado é CRLF.
