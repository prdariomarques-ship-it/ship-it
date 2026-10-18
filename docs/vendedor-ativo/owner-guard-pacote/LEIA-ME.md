# Guarda de atividade do dono + alerta ao dono por outra linha (código REAL de produção)

**Contexto (18/10/2026):** o `handlers.py` da VPS não tem a pausa por atividade do dono que o candidato do repositório tem; só o Gêmeo respeita o dono (`orchestrator/twin_policy.py`, `TWIN_OWNER_PAUSE_MINUTES`, 6 min). No contato 154 a B2B respondeu 4 s depois dos áudios do dono. Esta mudança foi escrita contra o texto exato das funções de produção (fixture `prod_fixture_handlers.py`, colhido em 18/10).

## O que faz
- **`services/owner_activity.py`** (novo): "dono ativo" = mensagem de SAÍDA com `sent_by_human=True` e sem ser autopilot, no mesmo contato e na mesma linha, dentro da janela. Não exige texto: áudio, PDF, imagem e localização contam (mesma definição do Gêmeo). Janela por agente em `/app/owner_activity_windows.txt` (`default=360`, `b2b=`, `azusa=`, `store=`; segundos; `0` desliga; lido a cada decisão, sem reiniciar). **Padrão 360 s (6 min)**, o mesmo valor do Gêmeo (`TWIN_OWNER_PAUSE_MINUTES=6`): uma regra só para os quatro agentes. A janela é inclusiva (360 s ainda suprime, 361 s libera) e cada nova mensagem do dono a reinicia. **Atenção:** a guarda só suprime, não reagenda; quem escreve durante a janela não recebe resposta do agente depois. Para um agente específico, mude a linha dele no arquivo (ex.: `b2b=120`; `0` desliga).
- **6 edições ancoradas no `jobs/handlers.py`:** (1) B2B/Azusa conferem o dono ANTES de gerar; (2) idem a loja, só no caminho do LLM; (3) a resposta enfileirada leva uma marca; (4) `send_whatsapp_text` REVALIDA imediatamente antes de transmitir (pega o dono que entrou durante a geração); (5) ao suprimir grava o log `owner_activity_guard` / `suppressed_owner_active` com agente, contato, id da mensagem do dono, mídia, janela e fase (`pre` ou `send`); (6) envio sem linha explícita ao telefone do dono (alerta do Gêmeo, anti-loop) sai por outra linha no ar quando o vigia viu a da loja fora (≤10 min).
- Substitui o pacote `alert-routing` (aquele mirava um trecho que não existe em produção; o script abortou sem tocar em nada).

## Decisões e limites (documentados de propósito)
- **Confirmação de pedido da loja não é bloqueada** (tem efeito real); só a resposta gerada pelo LLM é.
- **Respostas automáticas do WhatsApp Business** (ausência/saudação) saem com `sent_by_human=true` e CONTARIAM como atividade do dono (o Gêmeo já funciona assim). O dono as removeu no aplicativo; se voltarem, o agente fica calado até a janela passar.
- Instância pessoal / Gêmeo: caminho intocado.
- O que o dono escreve só vale depois que o webhook grava a mensagem; a revalidação no envio reduz, mas não elimina, a janela de corrida de alguns segundos.
- A guarda lê o banco; ela não substitui a pausa permanente (`conversation_control`) do candidato, que continua fora de produção (G03).

## Aplicar (reinicia o backend por segundos; exige o vigia já aplicado e o `line_watch.py` original dele)
scp da pasta para `/root/ownerguard`, `sed -i 's/\r$//' *.sh *.py`, conferir `SHA256SUMS`, `bash aplicar_na_vps_ownerguard.sh`. Desfazer: `bash rollback_ownerguard.sh`.
O script recusa sem tocar em nada se: algum arquivo da pasta foi adulterado, o `line_watch.py`/`line_watch_job.py` do container não forem os do vigia já aplicado, alguma das 6 âncoras não aparecer exatamente 1 vez no `handlers.py`, já estiver aplicado ou o container não estiver healthy. Ele não sobrescreve um `owner_activity_windows.txt` já existente. A verificação só LÊ (inclusive uma consulta real da atividade do dono no contato 154).

## Testes
`tests/test_owner_activity.py` (9, banco real) e `tests/test_owner_guard_prod_handlers.py` (11): as 6 edições aplicadas ao texto real e EXECUTADAS com banco real; só transporte, LLM e leitura de repositório simulados. Mutações verificadas: remover qualquer uma das 6 edições derruba testes; mídia sem texto, Gêmeo contado como dono, sem revalidação e sem isolamento por linha também. `harness_ownerguard.sh`: 12 casos com docker de mentira; **não** prova o Docker real nem o comportamento ao vivo.
