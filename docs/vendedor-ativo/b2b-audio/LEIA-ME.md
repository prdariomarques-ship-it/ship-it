# Áudio da instância b2b-sales (agente B2B passa a entender e responder áudios)

**Decisão do dono (17/10/2026):** liberar. **Estado:** código no repositório; **não aplicado na VPS**.

## Por que
Em 7 dias a `b2b-sales` recebeu 20 áudios, todos sem texto. Causa (confirmada no código de produção, `providers/whatsapp/evolution/provider.py` linha 184): `download_media` só aceita a instância da loja (`EVOLUTION_INSTANCE`) e a pessoal (`EVOLUTION_PERSONAL_INSTANCE`); qualquer outra devolve `None` sem erro, e o áudio é ignorado. O STT em produção (`STT_PROVIDER=local`, serviço `speech:8090`, em segundo plano) já funciona nas outras duas instâncias.

## O que muda
- Nova configuração `EVOLUTION_MEDIA_EXTRA_INSTANCES` (vazia no repositório). Na VPS o script grava o padrão `b2b-sales` em `config.py` (sem precisar de `.env`; a variável de ambiente continua mandando).
- `download_media` passa a aceitar as instâncias dessa lista. `azusa-church` e qualquer outra continuam bloqueadas.
- **Efeito para o cliente:** o agente B2B responde ao áudio em segundos, como responde texto. Hoje, no contato 154, quem respondeu os áudios foi o próprio dono (~1,5 min depois). Risco aceito: responder antes de o dono ouvir. As travas existentes (pausa quando o dono age, anti-promessa FICHA-M5) continuam valendo.
- Áudios antigos não são reprocessados.

## Aplicar (reinicia o backend por alguns segundos)
1. Cole `BLOCO_COLAR_NA_VPS.txt` na VPS (cria `~/b2b_audio`; deve terminar com `ARQUIVOS CONFEREM`).
2. `cd ~/b2b_audio && bash aplicar_na_vps_b2b.sh`
3. Desfazer: `bash rollback_b2b.sh`.

O script recusa sem tocar em nada se uma âncora não bater, se já foi aplicado ou se o container não estiver healthy; confere cada cópia dentro do container; reinicia; roda uma verificação sem rede (b2b-sales liberada, azusa-church bloqueada, loja intacta); qualquer falha devolve os arquivos e reinicia. `harness_b2b.sh` testa essa lógica com um docker de mentira (10 casos): **não** prova o comportamento do Docker real. O áudio sai pelo serviço local da VPS (nada vai a terceiros).
