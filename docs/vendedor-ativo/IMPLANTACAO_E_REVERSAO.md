# Implantação e reversão — PROCEDIMENTO PROPOSTO (nada disto foi executado)

Pré-requisitos que **não** estão resolvidos (bloqueiam qualquer janela): (1) cadeia Alembic **instalada** na VPS confrontada com o repositório (que desde 13/10 contém as revisões históricas recebidas no lugar do marcador vazio de `9e2f1c6d7a80`; isso não prova o que está instalado) — `down_revision` de `c8f3a1d27b40` aponta para `e610080003` (cabeça do repositório) e a cabeça de produção coletada é `9e2f1c6d7a80`; (2) versão do Evolution instalada e reprodução de voz **no aparelho**; (3) máquina para o serviço de voz (a VPS tem ~268 MB livres; candidato: o PC do proprietário com RTX 3060 12 GB, que precisa estar ligado e alcançável pelo backend por VPN/túnel — isso é uma dependência operacional a decidir); (4) escuta e aprovação das amostras pelo proprietário; (5) revisão externa deste ramo; (6) decisão sobre a convivência das três linhas (coleta de produção × PR #63 × FH). Esta documentação não autoriza deploy.

## A. Ordem proposta (cada passo reversível e verificável antes do próximo)
1. **Backup** do banco e da configuração; registrar a cabeça Alembic instalada (`alembic current`) e o `\d` de `contacts`, `messages`, `store_quotes`.
2. **Serviço de voz em outra máquina** (`voice-service/`, `docker-compose.example.yml`): rede interna, tokens novos, pesos com revisão fixada, perfil `loja` criado com `scripts/prepare_reference.py` (consentimento declarado). `GET /readyz` com o token deve devolver `ready: true`.
3. **Migração `c8f3a1d27b40`** (duas tabelas novas, sem tocar nas existentes) — só depois de confirmar `down_revision`. Verificar com `alembic upgrade --sql` antes.
4. **Código do backend** com `STORE_VOICE_ENABLED=false`, `STORE_FOLLOWUPS_ENABLED=false` e `STORE_HOURS_CONFIRMED=false`. Reiniciar somente o backend. **Não é idêntico ao atual**: mesmo com as duas chaves desligadas, no fluxo da loja já habilitado (a) "PARAR", recusa e "só texto" passam a ser reconhecidos antes do agente, gravados (`store_contact_opt_out`, `store_followup_opt_out`, pausa por recusa, `reply_mode`/`voice_opt_out`) e confirmados ao cliente por texto; (b) um pedido afirmativo de áudio ("quero áudio") grava `reply_mode="audio"` e limpa um "só texto" anterior, sem interceptar a conversa; (c) o agente ganha a ferramenta de horário (resposta qualificada como não confirmada enquanto `STORE_HOURS_CONFIRMED=false`); (d) o envio de texto passa a ser reservado também por identidade de acompanhamento quando o payload traz `followup_id` (não ocorre sem o scanner). Se isso não for desejado na primeira etapa, é preciso uma chave própria — hoje não há.
5. **Voz em sombra:** ligar `STORE_VOICE_ENABLED=true` apenas com um contato de teste do próprio proprietário (preferência `reply_mode=audio`), conferir áudio no aparelho, recibo, eco sem pausar a conversa, texto antes do áudio.
6. **Acompanhamentos:** `scripts/store_followups.py plan` e `run` (simulação) por alguns dias; só então `--apply` com `STORE_FOLLOWUPS_ENABLED=true`, **manualmente**, em lotes pequenos. Não há agendador; criar rotina é decisão separada.

## B. Reversão
- Voz: `STORE_VOICE_ENABLED=false` (o texto continua saindo; jobs de voz pendentes são cancelados ao rodar: gate "voz desligada"). Linhas `needs_review` permanecem como evidência.
- Acompanhamentos: `STORE_FOLLOWUPS_ENABLED=false`; cancelar `scheduled` pendentes com SQL revisado (`status='cancelled', cancel_reason='reversão'`). Nunca apagar linhas já enviadas.
- Backend: voltar à imagem anterior (as colunas/tabelas novas são ignoradas por ela).
- Migração: `alembic downgrade -1` **recusa** se as tabelas tiverem linhas (histórico de envios); em reversão com dados, exportar e decidir manualmente. Sem `stamp`.
- Serviço de voz: parar o contêiner; o backend passa a tratar indisponibilidade como "sem áudio" (o texto já foi enviado).

## C. Verificações de pós-implantação (só leitura)
`store_voice_sends` por estado (`needs_review` precisa de triagem humana: nunca reenviar por script); `store_followups` por estado e motivo de cancelamento; ausência de envio pela instância pessoal; contagem de áudios por contato/dia dentro do limite.
