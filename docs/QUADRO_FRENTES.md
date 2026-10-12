# Quadro único das frentes (candidatas isoladas)

Atualizado em 2026-10-12. Ramo: `feat/vendedor-ativo-voz` (base `5372c27` = `chore/next-16.4-security`). **Nada aqui está implantado**; implantação continua dependendo das verificações e aprovações de produção.
Legenda: ✅ feito e testado na candidata · 🟡 feito com ressalva · ⛔ bloqueio concreto (isolado; o resto segue) · ⏳ não iniciado (com o motivo).
Código/commit: hashes são do ramo; "este lote" = commit `feat(agents+voz): …` (ver `git log --grep "este lote"` ou `git log -- <arquivo>`).

## Frente 1 — Agentes existentes (Loja, Twin pessoal, B2B, Azusa; separados)

| Pendência | Estado | Código / commit | Teste | Bloqueio ou decisão |
|---|---|---|---|---|
| Pausa humana antes do transporte | ✅ | `services/conversation_control.py`, `jobs/handlers.py` (PR #63, já na base `5372c27`) | `tests/test_whatsapp_send_queue_retry.py`, `whatsapp_agents_fix/*` | Limite conhecido: pausa é checada no envio; envio antigo após um `resume` não é barrado por revisão (só o Twin tem essa cerca) |
| Duplicidade na fila / retentativa | ✅ | reserva por job (PR #63) + identidade estável por acompanhamento (`7b221b9`) | `test_followup_claim_postgres.py` (PostgreSQL real), `test_parecer_vendedor_ativo.py` | — |
| Mensagem antiga não recebe resposta automática | 🟡 | `jobs/handlers.py::_message_too_old`, `AUTO_REPLY_MAX_MESSAGE_AGE_SECONDS` (este lote) em Loja, B2B, Azusa e Twin/pipeline; PARAR/recusa antigos continuam honrados | `tests/test_message_age_guard.py` (7, handler real) | **Desligado por padrão (0)**: o dono decide o limiar (sugestão a avaliar: 1800 s) |
| Loop de resposta | 🟡 | `_loop_guard_or_alert` já existe na base e cobre Loja/B2B/Azusa/pipeline | testes da PR #63 | Generalização à base de produção ⛔ (config/handlers de produção divergentes) |
| Opt-out/recusa na Loja | ✅ | `services/store_optout.py` (`021b8b6`, `7b221b9`) | `test_store_optout.py`, `test_parecer_vendedor_ativo.py` | — |
| Opt-out em B2B/Azusa/Twin | ⏳ | — | — | **Decisão de desenho**: `Contact.preferences` é compartilhado entre instâncias; um PARAR no B2B gravaria a chave da Loja e vice-versa. Precisa de chave por fluxo antes de implementar |
| Autoria correta (incidente Flávio/Micael) e contexto | ⛔ | — | — | Faltam os arquivos reais de produção: `planner.py`, `store_agent.py`, `descriptions.py`, `context.py`, `utils/config.py` |
| Eco antes do recibo | ⛔ | parcial (PR #63 rodada 7) | — | Decisão do dono: pausar na ambiguidade (atual) ou adiar a classificação |
| Pós-venda/FH (drenagem, piso de agendamento, validação de atraso) | ⛔ | FH4 + errata aceitos estaticamente no parecer; **não estão no git** (zips) | resultados do autor nos zips | Faltam `adendo-fh4-v12.zip` e `adendo-v12-desempate-mesmo-segundo.zip` aqui; coleta somente leitura da cadeia instalada; esquema/versão/volume do PostgreSQL de produção. `services/store_aftercare.py` não existe nesta linha (o handler base o importa) |

## Frente 2 — Vendedor ativo da Loja

| Pendência (parecer 12/10) | Estado | Código / commit | Teste |
|---|---|---|---|
| Envio após PARAR (job já enfileirado) | ✅ | `store_followups.send_guard` + `reserve_plain_send(guard=)` (`7b221b9`) | `test_parecer_vendedor_ativo.py` (zero chamadas ao provedor) |
| Duplicidade concorrente | ✅ | claim atômico (`7b221b9`) | PostgreSQL 16 real, 2–3 sessões com barreira |
| Pedido de áudio × recusa de áudio | ✅ | `store_optout` (`7b221b9`) | classificação + handler real |
| Horário provisório, margem, data, fuso | ✅ | `STORE_HOURS_CONFIRMED=false`, validações (`7b221b9`) | testes de config/ferramenta/planner |
| Roteiro final × limite do serviço; download com limite; atualidade na reserva da voz | ✅ | `store_voice`, `voice_client` (`7b221b9`) | `test_parecer_vendedor_ativo*.py` (28/28 mutantes mortos) |
| Horário confirmado pela equipe | ⛔ | — | Decisão/dado: a equipe da loja confirma; depois `STORE_HOURS_CONFIRMED=true` |
| `store_agent.py` de produção com a ferramenta de horário | ⛔ | — | arquivo de produção não coletado |
| Migração na cadeia de produção (head `9e2f1c6d7a80` × repo `e610080003`) | ⛔ | `c8f3a1d27b40` aponta para a cadeia do repo | coleta somente leitura da cadeia instalada |
| Pós-venda por voz | ⏳ | — | depende da linha FH fora do git |
| Contrato do Evolution instalado e reprodução como mensagem de voz | ⛔ | `EvolutionProvider.send_voice` (contrato de documentação de terceiros) | versão instalada e teste em aparelho |

## Frente 3 — Voz e painel (reutiliza o `voice-service/`)

| Pendência | Estado | Código / commit | Teste |
|---|---|---|---|
| Serviço de voz (token por agente, perfil com consentimento, fila limitada, OGG/Opus, TTL) | ✅ **com motor simulado** | `voice-service/` (`f7fa5c1`) | 54 → 65 testes, mutantes 20/20 |
| Painel web sobre o mesmo serviço (`/panel`, `/v1/panel/status`) | ✅ **com motor simulado** | `voice-service/app/panel/*`, `app/main.py`, `service.py::recent` (este lote) | `tests/test_panel.py` (11) + navegador real (Chromium headless, `scripts/e2e_painel.cjs`): conectar, gerar, tocar, rótulo "simulado" |
| **Áudio real com a sua voz** | ⛔ | adaptadores Chatterbox/Qwen3 escritos contra a API lida no pacote, **nunca carregaram pesos** | — |

Bloqueios concretos da voz real (isolados; não travam as outras frentes): (1) a gravação `WhatsApp Ptt 2026-10-12 at 13.39.29.ogg` não está no ambiente; (2) `huggingface.co` bloqueado pela política de rede do ambiente (não contornado) — ou rodar `scripts/make_samples.py`/`measure.py` no PC do dono; (3) licença dos **pesos** a conferir nos cartões oficiais; (4) validação por escuta e desempenho na máquina escolhida. O painel **não resolve** as falhas de envio pelo WhatsApp: ele não envia nada.

## Decisões do dono (pendentes)
1. Limiar de mensagem antiga (`AUTO_REPLY_MAX_MESSAGE_AGE_SECONDS`). 2. Eco antes do recibo: pausar ou adiar. 3. Chave de opt-out por fluxo (B2B/Azusa/Twin). 4. Horário confirmado pela equipe. 5. Onde hospedar o voice-service (PC com RTX 3060 é o candidato; a VPS não tem RAM).

## Segurança
A chave Groq que apareceu na transcrição do DSH precisa ser trocada (nunca copiada para o repositório).
