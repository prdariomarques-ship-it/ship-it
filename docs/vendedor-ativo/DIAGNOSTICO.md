# Vendedor ativo da Loja Marquescolor — diagnóstico com evidências

Data: 2026-10-12. Escopo: transformar o agente da loja em vendedor ativo, com resposta por voz (voz autorizada do proprietário) enviada pelo Evolution.
Regra de leitura: **código existente ≠ teste executado ≠ implantação comprovada**. Nada abaixo afirma implantação; nenhum acesso à VPS, ao banco de produção ou a mensagens reais foi usado.

## 1. Fontes e versões (o que cada afirmação se apoia)

| Fonte | Versão / identificação | Natureza |
|---|---|---|
| Repositório `prdariomarques-ship-it/ship-it`, ramo-base de trabalho `chore/next-16.4-security` | `5372c27` (inclui PR #63 não mergeada: pausa, recibos, reserva de envio) | código no repositório |
| Ramo designado `claude/dario-os-platform-gcg6i2` | `0fab8cb` — linha **separada** (57 commits próprios, 135 atrás do ramo-base; sem `conversation_control`, sem `store_*`) | código no repositório |
| Arquivos de produção coletados (pacotes locais `aftercare-review.tgz`, `aftercare-deps.tgz`, `aftercare-deps2.tgz`) | SHA-256 `a0825e54…`, `b9288204…`, `fac652d8…` (107 arquivos). `jobs/handlers.py` = `d49034ee…`; `webhooks/router.py` = `7da0966f…` | coletados da VPS pelo proprietário; **não** provam o que roda hoje |
| `handlers.py.txt` / `router.py.txt` / `darius_twin.py.txt` | `1e8571b9…` / `7da0966f…` / `c9351131…` (idênticos ao baseline `2ff7f4b` do PR #63, o primeiro com a frase do Twin alterada localmente) | arquivos enviados |
| Correções FH (pós-venda) e adendos | `entrega-correcao-pos-venda-v12.zip` `4a828be5…`; **mais recentes:** `adendo-fh4-v12.zip` `5047c721…` + `errata-fh4-v12.zip` `8c066882…` (aceitos na revisão estática do FH4); adendo do desempate `1aff617d…` (**ainda sem revisão independente**) | pacotes entregues; **não estão no git** |
| `SESSION_TRACKING.md` (2026-10-10) | último registro da PR #63, rodada 7 | documentação: **parcialmente desatualizada** (ver §4) |

## 2. Matriz de capacidades

| Capacidade | Evidência e versão | Estado | Lacuna comprovada |
|---|---|---|---|
| **Catálogo, preço, estoque** | `models/product.py` (`sku`, `unit_price`, `stock_quantity`, `active`), `repositories/product.py` (`search_by_name`, `get_by_sku`) no repositório e na coleta; ferramentas `list_products`/`search_products` em `agents/tools/domain.py` | existe | **Quantidade de produtos não confirmada** (326 e OpenWA não são estado atual). `services/store_catalog.py` não existe em nenhuma fonte; o job `catalog.index_product` não tem produtor e chama métodos inexistentes (`MemoryManager.index_product/deindex_product`: 2 erros de tipo conhecidos). |
| **Cadastro e identificação de clientes** | `models/store.py::StoreCustomer` (telefone, `orders` JSON, `segment`); `Contact` por telefone; coleta: `services/store_sales.resolve_customer` (cliente da conversa por telefone) | existe | **Incidente Flávio/Micael** (SESSION_TRACKING): o agente não lê `Contact.name` do banco. Correção depende de `store_agent.py`/`planner.py`/`descriptions.py`/`context.py`/`config.py` **de produção, não coletados** (hashes divergem do repositório). Não corrigido aqui. |
| **Orçamentos** | Produção (coleta): `services/store_sales.py` — `StoreQuote` persistido, validade de 30 min, código `CONFIRMAR <12 hex>`, itens/quantidades validados contra catálogo e estoque. Repositório: `create_quote` do agente é só cálculo (sem persistência) | existe em produção (coleta); **o repositório não tem** | O repositório está atrás da coleta: `store_sales.py`, `StoreQuote` e `repositories/store.py` ausentes. Validade de 30 min implica que **todo orçamento vence antes de qualquer retomada** (retomada = refazer, não confirmar o antigo). |
| **Confirmação de compra / pedidos** | Coleta: `confirm_quote` (reserva atômica, idempotente, baixa de estoque, pedido em `StoreCustomer.orders`); `handlers.py` só aceita o código vindo da mensagem **persistida do cliente** | existe em produção (coleta) | No repositório a ferramenta `record_order` fica exposta ao LLM, protegida só por instrução no prompt. Em produção o fluxo por código cobre a confirmação; **o prompt de produção (`store_agent.py`) não foi coletado**, então se `record_order` continua exposta é desconhecido. |
| **Acompanhamento comercial** | Coleta: `store_loop.py` (metas do cliente: orçamento/pedido/suporte, só conclui com resultado verificado); nenhum acompanhamento **proativo** além do pós-venda | parcial | **Não havia** retomada de orçamento nem sugestão de reposição, nem fila/estado/limites de acompanhamento proativo. |
| **Pós-venda** | Coleta: `store_aftercare.py` (24 h após entrega **confirmada por operador**, 1 mensagem, opt-out `PARAR POS-VENDA`, reclamação aberta cancela, claim antes do envio, incerto → `needs_review`). Endurecimento FH (pausa humana, opt-out durável, reservas `effect_claims`): **pacotes FH4+errata, fora do git** | existe; endurecimento revisado | FH **não implantado**; a cadeia Alembic real, esquema e versão do PostgreSQL de produção seguem pendentes. Texto só (sem voz). |
| **Transcrição de áudio** | Coleta: `providers/stt/factory.py` referencia `OpenAIWhisperProvider` e `LocalWhisperProvider`; `base.py` (contrato); **as duas implementações não estão na coleta**. Repositório: fábrica **vazia** por decisão da PR #63. `webhooks/router._transcribe_audio` e job `whatsapp.transcribe_audio` existem | referenciado, **implementação não verificada** | Não há prova de qual backend STT roda, nem de qualidade. |
| **Envio de mídia pelo Evolution** | Repositório: `EvolutionProvider.send_image/send_file/send_audio(url)` — `message/sendMedia`, `message/sendWhatsAppAudio` com corpo plano `{number, audio}`; coleta tem `download_media` (`chat/getBase64FromMediaMessage`) **que o repositório não tem** | existe (URL); base64 não | **Versão instalada do Evolution não confirmada** (só `docker/.env.example`). Reprodução como mensagem de voz **só se confirma no aparelho**. Nenhuma geração de voz existia: `grep` por TTS/ElevenLabs no repositório = só o nome do método `sendWhatsAppAudio`. |
| **Fila, tentativas, deduplicação, pausa humana** | Repositório (PR #63): worker com CAS, `conversation_control` (pausa, `claim_send`, `reserve_plain_send` por job, recibos), `incident_dedup`. Coleta: worker original (sem essas reservas). FH: `effect_claims` | existe, **em linhas diferentes** | Três linhas não unificadas: coleta (produção), PR #63 (não mergeada), FH (não implantada). Lacuna registrada no tracking: pausa humana **não** barra envios já enfileirados de Loja/B2B/Azusa (envio comum só tem a reserva por job). |
| **Twin (`darius_twin.py`)** | `c9351131…`: monta mensagens ao LLM no estilo do proprietário; **nenhuma geração de áudio** | existe (texto) | Não é o vendedor da loja; permanece separado (instância pessoal, `whatsapp_twin_mode_enabled`). |
| **Voz sintética** | — | **não existia** | Criada nesta etapa (`voice-service/`). |

## 3. Testes: o que **eu executei** nesta etapa × o que só foi relatado

Executados por mim, neste ambiente (Python 3.11, 4 vCPU, 15 GiB RAM, **sem GPU**), dados sintéticos, SQLite isolado:

- `backend/tests` no ramo-base **antes** de qualquer mudança: **1144 passaram** (3 min 53 s); **depois** das mudanças: **1331 passaram**.
- `ruff check` e `mypy` (mesma configuração da CI): ruff limpo; mypy = **12 erros pré-existentes** (módulos de produção ausentes, `psutil` sem stubs) — **nenhum novo**.
- Relatados por terceiros/entregas anteriores, **não reproduzidos agora**: 153 testes de `whatsapp_agents_fix/`; resultados da PR #63; CI do GitHub. Os 229 testes do FH4 foram reproduzidos **em rodada anterior desta sessão** (PostgreSQL descartável), não agora.

Implantação comprovada: **nenhuma** (nenhuma fonte prova o que roda na VPS; `darioos-evolution-backend-1` e o banco `darioos_cutover_20260927` constam só nas anotações do proprietário).

## 4. Documentação × realidade (o que está desatualizado)

- `SESSION_TRACKING.md` diz que `WhatsAppProvider.download_media` e o STT "não existem": **na coleta o provider de produção tem `download_media` e a fábrica de STT referencia dois backends**. Estado do repositório ≠ estado da coleta.
- `SESSION_TRACKING.md` dá `Contact.awaiting_reply_since` como sem migração: a coleta traz a migração `c91d5e7a3b20_twin_autopilot_fields` — **existência do arquivo ≠ coluna no banco**; segue sem confirmação de `\d contacts`.
- A cadeia Alembic coletada termina em `9e2f1c6d7a80`; a do repositório termina em `e610080003` (PR #63). `down_revision` da migração nova está apontado para a cabeça **do repositório** e precisa ser reconfirmado antes de qualquer implantação (sem `stamp`).

## 5. Decisões de integração tomadas

1. Base: ramo-base `chore/next-16.4-security` (único que tem as proteções da PR #63 a preservar: pausa humana, reserva de envio por job, recibos). O ramo designado `claude/dario-os-platform-gcg6i2` é uma linha diferente e não serve de base; **não foi usado para push** (ver relatório).
2. Os modelos de produção que o repositório não tem (`StoreQuote`, `StoreDelivery`, `StoreSupportCase`) foram **importados verbatim da coleta** em commit separado (baseline), como a PR #63 fez com `handlers.py`/`router.py`.
3. As correções FH **não foram tocadas nem reimplementadas**: o vendedor ativo é aditivo (módulos novos) e só usa a convenção de opt-out `store_followup_opt_out` que o pós-venda de produção já respeita.
4. Tudo novo nasce **desligado** (`STORE_VOICE_ENABLED`, `STORE_FOLLOWUPS_ENABLED`), sem rotina agendada.

## 6. Material local enviado pelo proprietário (transcrição de outra sessão de agente)

Arquivo recebido: `dsh-session-session-08d9e487-….zip` (234 218 bytes, SHA-256 `7019d5a9…`), contendo `session.v4.jsonl` — a transcrição de uma **sessão de outro agente** (cwd `C:\Users\dario\OneDrive\chatbot-tintas`) que tentou a mesma tarefa em 12/10. É **dado reportado por terceiro, não verificado por mim**. Usei apenas fatos de leitura direta registrados nela:

| Fato | Registro na transcrição | Uso |
|---|---|---|
| Hardware do PC do proprietário: **Ryzen 7 5700X (8C/16T), 32 GB RAM, NVIDIA RTX 3060 12 GB** (≈4,9 GB de VRAM ocupados por outros programas na hora da leitura) | saída de `Get-CimInstance`/`nvidia-smi` | candidato real a hospedar o serviço de voz (a VPS não serve). **Não medi nada neste hardware.** |
| A gravação `WhatsApp Ptt 2026-10-12 at 13.39.29.ogg` **não está** em OneDrive, Desktop, Documents nem Downloads desse PC | busca recursiva registrada; o agente concluiu "não localizada" | confirma que ela precisa ser anexada |
| `chatbot-tintas`: bot mínimo (Groq + Evolution `sendText`), `docker-compose` com `atendai/evolution-api:latest` | leitura de `bot.py`/`docker-compose.yml` | **versão do Evolution local não é fixada** (tag `latest`): a versão real continua desconhecida |
| O clone local do `ship-it` estava no ramo `claude/dario-os-platform-gcg6i2` (sem `products`, sem STT, sem `conversation_control`) | leitura de arquivos | **consistente** com o que achei: esse ramo é uma linha antiga; o ramo-base correto para este trabalho é `chore/next-16.4-security` |

Não adotei: números de VRAM/RAM por modelo e "licença dos pesos MIT/Apache" afirmados na transcrição **sem fonte citada**; a lista de arquivos de `Downloads` (apenas confirma a existência local dos pacotes FH). **Aviso de segurança:** a transcrição contém, em saída de ferramenta, o conteúdo de um `.env` com uma **chave de API (Groq)** em texto puro. Recomendo **revogar/rotacionar essa chave** e não reenviar esse arquivo. Não copiei o valor para lugar nenhum e removi a cópia extraída que eu havia feito.
