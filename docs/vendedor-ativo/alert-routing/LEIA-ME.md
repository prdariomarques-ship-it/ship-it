SUPERSEDED: este pacote foi substituído por docs/vendedor-ativo/owner-guard (o ponto de edição daqui não existe no handlers.py de produção).
# Alertas ao dono por outra linha quando a da loja cai

**Por quê:** os alertas do Gêmeo ("Mensagem sensível... não foi respondida") e do anti-loop saem pela linha PADRÃO (a loja), por desenho. Na queda de 16/10 (15:50–madrugada), dois deles (Claudio Lasakosvitsch às 17:14 e "❤️" às 19:59, horário de Brasília) não chegaram ao dono.

**O que muda:** `services/line_watch.py` guarda o último estado das linhas lido pelo vigia; `alert_instance()` devolve outra linha no ar (preferindo uma que não seja a pessoal) SÓ quando a linha padrão aparece fora do ar numa leitura de até 10 min; senão devolve None e tudo segue como antes. O `jobs/handlers.py` ganha UMA edição ancorada: em envio de alerta ao proprietário sem `instance` explícita, usa essa linha. Não há chamada de rede no caminho do envio. Envios comuns e instâncias explícitas nunca são redirecionados.

**Aplicar (reinicia o backend por segundos; exige o vigia já aplicado):** copie a pasta por scp para `/root/roteamento`, `sed -i 's/\r$//' *.sh *.py`, confira `SHA256SUMS`, `bash aplicar_na_vps_roteamento.sh`. Desfazer: `bash rollback_roteamento.sh`. O script recusa sem tocar em nada se: o `line_watch.py`/`line_watch_job.py` do container não forem exatamente os do vigia já aplicado, se a âncora do `handlers.py` não aparecer 1 vez, se já foi aplicado, ou se o container não estiver healthy.
Testes: `tests/test_alert_routing.py` (3, worker e handler reais com transporte simulado; 2 mutações derrubam testes) e 2 novos em `tests/test_line_watch.py`. `harness_roteamento.sh`: 11 casos com docker de mentira; não prova o Docker real.
Limite: o estado fica em memória do processo; logo após um reinício, até a próxima rodada do vigia (≤2 min), alertas saem pela linha padrão como antes.
