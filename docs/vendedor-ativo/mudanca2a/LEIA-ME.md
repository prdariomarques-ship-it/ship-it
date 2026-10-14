# Mudança 2 (parte A) — patch sobre a produção, sem migração de banco

Autorizada pelo dono em 14/10/2026 ("pode realizar a mudança de dois e a mudança de três"). Executada pelo dono na VPS.

## O que muda (só `jobs/handlers.py` e `services/messaging.py` do container do backend)
1. **Eco antes da gravação deixa de virar "humano".** O envio passa a guardar o id do WhatsApp devolvido pelo gateway (`key.id`). Se o eco
   (`fromMe`) já tinha gravado a linha como humana, a linha é corrigida para "do app" em vez de duplicada. Sem coluna nova.
2. **Pausa de 30 min quando uma PESSOA atua** na conversa (contato + instância): Twin, Loja, B2B, Azusa e pipeline geral. Apresentações do
   próprio robô gravadas como humanas não contam. Janela em `/app/human_pause_minutes.txt` (vale na hora, sem reiniciar; `0` desliga) ou
   `HUMAN_PAUSE_MINUTES`; padrão 30.
3. **Descarte no envio** se uma pessoa escreveu depois de o agente começar a gerar a resposta (`_guard_started_at`/`_guard_contact_id`).
4. **Áudio suspeito não vira resposta:** Twin — transcrição com menos de 5 palavras, frase típica de alucinação do Whisper ou repetição em
   laço vira alerta ao dono ("responda você mesmo"), sem resposta ao contato; Loja — só frase de alucinação/laço, silêncio com registro.
5. **Dado de contato inventado não sai** pelo Twin (e-mail, link, telefone/documento que não esteja na conversa; o e-mail do dono é
   permitido via `TWIN_ALLOWED_CONTACT_DATA`, padrão `dariomneto@hotmail.com`).

## Como foi verificado
- Os 9 arquivos de produção foram reconstruídos aqui a partir do que a VPS devolveu e **conferidos por sha256** (`handlers.py` f7b07719…,
  `router.py` 7da0966f…, `provider.py` 136e56fd…, `base.py` b47c211e…, `service.py` d64ac85a…, `messaging.py` 5b72aae2…,
  `models/message.py` 5615698f…, `repositories/message.py` 33c8ee56…).
- `aplicar_m2a.py` aplica substituições exatas (cada trecho tem de existir exatamente uma vez), confere o hash de origem e o hash de
  resultado (`handlers.py` 38561a2e587105e2, `messaging.py` 42397ce3f0bd22d0) e aborta sem gravar nada se algo divergir.
- `test_m2a_producao.py`: 21 testes passam com os arquivos de produção já corrigidos, sobre uma cópia da candidata (SQLite). Cinco mutantes
  (pausa desligada, sem descarte no envio, eco não corrigido, dado inventado liberado, áudio curto liberado) são mortos pelos testes.

## O que NÃO está provado
- Comportamento no PostgreSQL e no Evolution reais; o portão de risco de produção (`orchestrator/twin_risk_gate.py`) não estava na cópia
  (substituído nos testes por um dublê com a assinatura de produção); a verdade só vem da observação depois de aplicar.
- Mensagens da Loja automatizadas por outros caminhos (pós-venda) e gravadas como humanas ainda contariam como "pessoa atuou"; por isso o
  arquivo de janela permite desligar a pausa na hora.

## Reversão
`rollback.sh` (gerado junto da aplicação) devolve os dois arquivos originais e reinicia o backend. Nada de banco foi alterado.
