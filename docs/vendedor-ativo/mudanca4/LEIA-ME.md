# Mudança 4 — contatos silenciosos do Twin (candidata; NÃO aplicada)

Para os contatos listados em `/app/twin_silent_contacts.txt` (dentro do container), o Twin **não responde** e o dono recebe o alerta imediato (mesmo caminho do portão de risco, motivo "contato prioritário (família/chefe)"). Vários recados seguidos do mesmo contato geram **um** alerta por 10 minutos. O arquivo é relido a cada mensagem: mudar a lista **não** reinicia nada. Arquivo ausente ou vazio = comportamento atual.

Formato da lista: uma entrada por linha (ou separadas por vírgula); id do contato (até 7 dígitos) ou telefone em qualquer formato; `#` comenta.

- `aplicar_m4.py`: 3 substituições exatas no `handlers.py` de produção **já com a 2A** (entrada `bf3ff6b7…`, saída `9eb1e67c…`).
- `scripts-aplicacao/aplicar_na_vps_m4.sh`: confere hashes, copia para nome temporário, grava a lista (recusa se já existir), troca, **reinicia o backend**, verifica dentro do container e reverte sozinho se falhar. `rollback_na_vps_m4.sh` volta ao `handlers.py` anterior.
- `test_m4_producao.py` + `rodar_testes_m4.sh`: 6 testes novos sobre os arquivos reais de produção (35 com os da 2A); três mutações do patch são reprovadas. `scripts-aplicacao/harness_m4.sh`: 9 cenários dos scripts com docker de mentira.

Limites: vive na camada gravável do container (quadro G03); só vale para o Twin (instância pessoal); não impede que o dono seja avisado de várias conversas ao mesmo tempo.
