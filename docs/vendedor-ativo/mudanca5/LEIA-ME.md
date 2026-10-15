# Mudança 5 (texto do Twin) — regra de compromissos (candidata; NÃO aplicada)

Só texto: acrescenta ao `twin_conversation.md` do container (`/app/agents/prompts/`) o bloco `FICHA-M5`, que proíbe o Twin de assumir compromissos em nome do Dário ("vou fazer", "pode deixar", "combinado", horários, prazos, pagamentos) e manda reconhecer e dizer que o Dário vê pessoalmente. Sem restart (o Twin lê o texto a cada resposta).

- `aplicar_m5.py`: acrescenta o bloco; aborta se ele já existe ou se o bloco da Mudança 3 não aparece exatamente uma vez.
- `aplicar_na_vps_m5.sh`: exige que o arquivo do container seja exatamente o da Mudança 3 (`ce47ba7e…fffc0d`), confere o novo dentro do container, troca com cópia `.m5_bak`, verifica com `load_persona_prompt` e devolve o original sozinho se algo falhar. `rollback_m5.sh` volta ao texto anterior.
- `harness_m5.sh` + `fakedocker.sh`: 10 cenários com docker de mentira.

Limite: é instrução ao modelo, não trava de código. O modelo pode, em algum caso, ainda escrever uma promessa. Para garantir, seria preciso um filtro de código sobre a resposta (candidato a Mudança 6). Contatos da lista silenciosa (Mudança 4) já não recebem resposta nenhuma.
