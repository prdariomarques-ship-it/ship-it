# Plano de implantação — correção dos agentes do WhatsApp (resumo público)

> Versão resumida para revisão via GitHub. A versão completa, com nomes
> de container, usuário/banco de produção e caminhos de backup reais, foi
> compartilhada apenas em canal privado com o dono do repositório —
> removida aqui por este ser um repositório público.

## Escopo

**Entra**: as 5 tabelas novas de `services/conversation_control.py`
(pausa, fencing de envio, fencing de alerta); o patch em
`jobs/handlers.py` (barreira de conteúdo interno, pausa humana
revalidada antes do transporte — incluindo mensagens já enfileiradas —,
deduplicação real de alerta); o patch em `webhooks/router.py`
(generalização do bloqueio de loop entre instâncias administradas);
fixar a correção numa nova imagem Docker e atualizar o arquivo de
Compose confirmado como ativo
(`/opt/chroma-migration-20260927/app.compose.prepared.json`, conteúdo
não incluído) para referenciá-la pelo digest.

**Não entra**: extensão do fencing de pausa a outros caminhos de envio
automático (B2B/Azusa/pós-venda/fluxo legado); testes com cliente real;
qualquer alteração de credencial/token/segredo; mudanças no frontend ou
no fluxo financeiro/Telegram.

## Status desta janela

- **Fase 0 (pré-voo, somente leitura)**: ✅ concluída. Confirmado: nenhum
  bind mount de código no container (vive na imagem); cadeia do Alembic
  em produção compatível com a nova migration, sem ajuste necessário;
  arquivo de Compose ativo confirmado pelas próprias labels do container
  (não por suposição).
- **Fase 1 (backup imediatamente antes da janela)**: ✅ concluída. Dump
  lógico do Postgres de produção verificado (íntegro, não vazio); ponto
  de retorno de imagem criado; arquivos originais salvos fora do
  container.
- **Fases 2 e 3 (implantação e validação)**: **não executadas**. Janela
  aprovada pelo dono do repositório, com ele mesmo como aprovador de
  rollback em tempo real — execução passo a passo, cada comando
  confirmado antes do próximo.
- **Fase 4 (rollback)**: critérios e comandos preparados, incluindo o
  aviso de que a migração mais recente bloqueia `alembic downgrade` por
  design (requer `DROP TABLE` manual, nunca automático, e só depois do
  rollback de código).

## Avisos importantes preservados do plano completo

- A migração mais recente (`e610080002`) **bloqueia downgrade
  automático** de propósito, para nunca perder auditoria de entregas já
  resolvidas — qualquer reversão de schema é manual, documentada, e só
  depois de revertido o código.
- O arquivo de Compose confirmado pina a imagem por **digest**, não por
  tag — a atualização pós-implantação preserva essa convenção.
- Não há confirmação de que esse arquivo de Compose não é regenerado
  automaticamente por algum processo de build/deploy não verificado
  nesta rodada — risco declarado, não assumido como resolvido.

**Nenhuma implantação, migração em produção, reinício de serviço ou
alteração de configuração foi executada.** Este PR é só para revisão de
código; a implantação segue um processo separado, com janela aprovada
e rollback preparado, fora do GitHub.
