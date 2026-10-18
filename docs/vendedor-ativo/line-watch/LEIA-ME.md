# Vigia das linhas do WhatsApp (alerta de queda)

**Por quê:** em 16/10/2026 a linha da loja (MARQUESCOLOR) caiu às 15:50 (`stream errored: conflict device_removed`, LOGOUT) e ficou ~12 h fora sem ninguém perceber: nenhuma regra do Prometheus cobria o estado das instâncias e os destinos do Alertmanager (`alerts@darioos` em localhost:587, webhook em localhost:5000) não chegam a você.

**Estado:** implementado e testado; **não aplicado na VPS**.

## O que faz
Job `lines.watch` (autorreagendável, mesmo padrão de `observation.tick`): a cada 120 s consulta `GET /instance/connectionState/<instância>` no Evolution para cada linha vigiada. Se uma linha ficar diferente de `open` por 2 rodadas seguidas (~4 min), enfileira um `whatsapp.send_text` para o seu telefone **por outra linha que esteja no ar** (prefere uma que não seja a sua pessoal). Lembrete a cada 60 min enquanto continuar fora; um aviso quando voltar. Se nenhuma linha estiver no ar, ou o Evolution não responder, só registra no log (não há por onde avisar). Um erro numa rodada nunca derruba a corrente.
- **Não toca** no provedor do WhatsApp nem no fluxo das mensagens: módulo aditivo.
- Atenção: o alerta chega pela linha B2B/Azusa (outro número). Se você **responder** a esse alerta, a resposta cai no agente daquela linha como se fosse um contato. O texto avisa "não responda".

## Aplicar (reinicia o backend por alguns segundos)
1. Cole `BLOCO_COLAR_NA_VPS.txt` na VPS (cria `~/line_watch`; deve terminar com `ARQUIVOS CONFEREM`).
2. `cd ~/line_watch && bash aplicar_na_vps_linewatch.sh` (pergunta o telefone que recebe o alerta, só dígitos com DDI, se não achar `WHATSAPP_OWNER_ALERT_PHONE` no container). Linhas padrão: `MARQUESCOLOR,b2b-sales,azusa-church,Dário Marques Neto` (mude com `LW_INSTANCES="a,b" bash ...`).
3. Desfazer: `bash rollback_linewatch.sh`.
O script lê config.py e main.py do container, aplica 2 edições ancoradas, cria 2 módulos, confere tudo dentro do container, reinicia, faz uma verificação que só LÊ o estado real das linhas (não envia mensagem), semeia o 1º job e confirma que ele existe. Qualquer falha devolve os arquivos, remove os módulos, apaga os jobs semeados e reinicia de novo.
`harness_linewatch.sh` testa essa lógica com docker de mentira (15 casos); **não** prova o comportamento do Docker real. Teste do backend: `tests/test_line_watch.py` (12; 5 mutações derrubam testes).

## Limites
- O estado "já avisei" fica em memória; o limitador (Redis) evita repetir o aviso se o backend reiniciar no meio de uma queda, mas o aviso de "voltou" pode se perder num reinício.
- Como todas as mudanças aplicadas à mão, os arquivos se perdem se o contêiner for recriado (G03); o job semeado fica no banco e, sem o módulo, vira erro "handler desconhecido" até o rollback.
