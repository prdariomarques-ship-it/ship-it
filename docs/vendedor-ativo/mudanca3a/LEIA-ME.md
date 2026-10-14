# Mudança 3 (texto do Twin) — aplicação

Só texto: `darius_twin.md` e `twin_conversation.md` dentro do container do backend (`/app/agents/prompts/`). O Twin lê os dois a cada resposta; **não reinicia nada**.

- `aplicar_m3a.py`: três trocas exatas no manual (identidade "Aqui é o Twin, assistente do Dário") + bloco `FICHA-M3A` no fim de `twin_conversation.md` (fatos autorizados, presença do Dário). Aborta sem gravar se um trecho não aparecer exatamente uma vez ou se o bloco já existir.
- `aplicar_na_vps_m3a.sh`: copia os originais para fora (`*.orig` + `hashes_antes.txt`), gera os novos, confere hash dentro do container, troca os dois juntos com cópia `.m3a_bak`, verifica com `load_persona_prompt` e devolve os originais sozinho se qualquer passo falhar.
- `rollback_m3a.sh`: devolve os originais (confere hash antes e depois).
- `harness_m3a.sh` + `fakedocker.sh`: testam a lógica com docker de mentira (8 cenários). Não provam comportamento em produção.

Observação: `load_persona_prompt` remove comentários HTML; por isso a verificação procura os títulos do bloco, não o marcador.
