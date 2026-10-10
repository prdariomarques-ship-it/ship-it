# Entrega — correção de marcador interno, pausa humana e deduplicação de incidentes (WhatsApp)

> Versão resumida para revisão pública via GitHub. A versão completa (com
> detalhes operacionais da VPS) foi compartilhada apenas em canal privado
> com o dono do repositório. Este repositório é **público** — nomes de
> container, usuário/banco de produção e caminhos de backup foram
> removidos ou generalizados aqui de propósito.

## 1. O que este PR resolve

A entrega anterior deste trabalho tinha um bloqueador deliberado:
`_incident_store()` em `jobs/handlers.py` levantava `NotImplementedError`
em vez de persistir de verdade. Esta rodada:

- Remove esse bloqueador por completo (não contorna, não captura a
  exceção).
- Reutiliza `services/conversation_control.py` de um candidato anterior
  (pausa/retomada com *fencing* por revisão, *claim* atômico de envio e
  de alerta — **estruturalmente separados** —, tratamento explícito de
  resultado incerto sem reenvio automático). Copiado verbatim, hash no
  `commit-base` deste PR.
- Reescreve `orchestrator/incident_dedup.py` para não ter armazenamento
  próprio: calcula de forma determinística qual `dedup_key` pedir ao
  `alert_claim` real.

## 2. Divergência de base — leia antes de revisar o diff

**Nenhuma branch deste repositório (master incluído, nem nenhuma branch
remota, nem histórico completo) contém o código real de produção para
`backend/jobs/handlers.py` / `backend/webhooks/router.py`.** Confirmado
por busca exaustiva em todos os blobs de todos os commits de todas as
branches/tags: nenhum bate com o hash dos arquivos reais coletados da
produção.

Por isso este PR tem **dois commits distintos, de propósito**:
1. **Commit "baseline"**: os arquivos de produção originais, sem nenhum
   patch, sem segredos, exatamente como coletados — importados neste
   repositório por aqui pela primeira vez.
2. **Commit "fix"**: a correção em si (patches, arquivos novos,
   migrations, testes), aplicada sobre o commit 1.

Isso deixa claro o que já existia em produção (commit 1) vs. o que esta
correção realmente altera (commit 2) — sem misturar os dois em uma única
mudança.

## 3. Separação de validação — três camadas, nunca a mesma prova

- **SQLite real**: testes que migram um banco SQLite real com as
  migrations reais e chamam `conversation_control.py`/`incident_dedup.py`
  de verdade (sem mock de banco).
- **PostgreSQL real, isolado**: testes opt-in (pulados sem uma variável
  de ambiente de conexão admin — nenhuma credencial fixa no código) que
  criam um banco descartável próprio, migram, testam concorrência real
  (dois e dez workers com pools de conexão separados), repetição, e
  sobrevivência a um reinício simulado (engine anterior descartado,
  engine novo do zero).
- **Handler real com provedor simulado**: `send_whatsapp_text` e o gate
  de instâncias administradas são importados como módulos Python reais
  (não reescritos, não só analisados por AST) através de uma árvore de
  stubs documentada (`app_stub/`, cada arquivo explica no próprio
  docstring o que substitui e por quê). O provedor WhatsApp é um fake que
  só registra chamadas — nunca envia nada de verdade. Um teste de
  "grupo de controle" confirma que uma mensagem comum, sem bloqueio
  algum, **alcança** o provedor, provando que os testes de bloqueio não
  estão simplesmente deixando de chamar nada.

## 4. O que NÃO foi testado (declarado explicitamente)

- Execução completa de ponta a ponta do webhook/handler contra os
  modelos ORM reais (Contact, Message, JobService) — não fazem parte dos
  arquivos de origem disponíveis.
- O provedor WhatsApp real (Evolution) — só um fake que nunca envia.
- Qualquer migração aplicada a um banco de produção.
- Qualquer envio a cliente real, número pessoal ou bot externo.
- Extensão do *fencing* de pausa humana aos caminhos de B2B/Azusa/
  pós-venda/fluxo legado — hoje só o Gêmeo Digital tem essa proteção.

## 5. Implantação

Um plano de implantação detalhado (backup, migração, validação,
critérios de rollback) foi preparado e parcialmente executado em modo
somente-leitura/backup (nenhuma mudança de comportamento em produção
ainda). A versão completa, com nomes de container e caminhos reais, foi
compartilhada em canal privado com o dono do repositório — não incluída
aqui por ser um repositório público.

O arquivo de Compose confirmado como realmente ativo (via labels do
próprio container, não por suposição) é:
`/opt/chroma-migration-20260927/app.compose.prepared.json` — seu
conteúdo não é incluído neste PR nem em nenhum arquivo público.

**Nenhuma implantação foi executada.** Este PR é só para revisão de
código.

## 6. Comandos de teste (rodar a partir da raiz deste pacote)

```bash
# Lógica pura / fakes (sem banco)
python3 -m pytest test_twin_risk_gate.py test_output_safety.py -v
python3 -m pytest test_incident_dedup.py -v -k "not real_store"

# Integração estrutural (AST sobre o arquivo real)
python3 -m pytest test_handlers_integration.py -v

# SQLite real (persistência e concorrência)
python3 -m pytest test_incident_dedup.py -v -k real_store
python3 -m pytest test_pause_fencing.py -v

# Handler real com provedor simulado
python3 -m pytest test_send_whatsapp_text_real_execution.py -v
python3 -m pytest test_administered_instance_gate.py -v

# PostgreSQL real e isolado (opt-in -- requer WHATSAPP_DEDUP_PG_ADMIN_URL)
export WHATSAPP_DEDUP_PG_ADMIN_URL="postgresql+asyncpg://<usuario>:<senha>@<host>/postgres"
python3 -m pytest test_dedup_key_postgresql_isolated.py -v
```

Resultado nesta sessão: 87 testes próprios, todos passando (os que
dependem de PostgreSQL rodaram com uma conexão admin local de teste, não
incluída aqui).
