# Patch de PRODUÇÃO (não aplicado) — papéis do Gêmeo

Arquivos reais recebidos em 24/10/2026 (cópias fiéis em `originais/`): `darius_twin.py` sha256 `c935113114ac5a71…` e `handlers.py` sha256 `ec6dd50c23ffae3d…`.

## O que muda
- `darius_twin.py` (4 edições ancoradas): importa `agents/darius_twin_roles.py`; a regra de papéis vai ao fim do prompt; a linha do contato diz "NÃO é o Dário"; a resposta passa por `guard_role_inversion` (tira apelido do dono usado como vocativo e a pergunta de saúde devolvida; se sobrar nada, `TwinReplyUnavailable`, que o handler já trata).
- `handlers.py` (4 edições): (1) import + (2) linha 447 do histórico passam a `build_twin_history(...)` (`[Dário]`/`[Gêmeo]` nas saídas de autoria conhecida); (3) **bloco de silêncio** antes do portão de risco: robô/menu/fila, alerta do próprio sistema e despedida pura (só se já falamos antes) → sem resposta, sem retenção, sem alerta; (4) **bloco de ato proibido** depois do guarda de compromisso: autorizar/emitir, pedir agência-conta-CPF, cobrar/reembolso, confirmar depósito sem comprovante, prazo assumido, "já segui" → cai no caminho de risco que já existe (retenção silenciosa + alerta com o rascunho).
- **Arquivos novos (3), puros e sem dependência dos outros módulos do Gêmeo:** `agents/darius_twin_roles.py`, `agents/darius_twin_actions.py`, `orchestrator/twin_silence.py`.
- **Interruptores por ambiente, no estilo dos guardas de produção:** `TWIN_ROLE_GUARD_ENABLED=false`, `TWIN_ACTION_GUARD=0`, `TWIN_SILENCE=0`.
- **Sem código:** a pausa quando o dono fala já existe (`silent_skip_reason`, `TWIN_OWNER_PAUSE_MINUTES=6`). Subir para 30 é só mudar a variável de ambiente.

## Por que vale: os guardas de produção atuais não pegam os casos reais
Os 223 envios automáticos reais de 16 a 23/10 passados pelos guardas REAIS de produção (`twin_finance_guard`, `twin_commitment_guard`, `twin_autoreply_gate`): **financeiro 0, compromisso 0, contraparte automática 2**. "Pode emitir", "Pode ser 10.", "agência, conta e CPF", "quero o reembolso", "tá ok" a depósito, "Já segui aqui" e os loops de 👋 passam por todos.

## Como foi verificado (sem VPS)
`python3 aplicar_twin_roles.py --origem originais --saida SAIDA` gera os dois arquivos (hashes fixados em `tests/test_twin_prod_patch.py`). `tests/test_twin_prod_handler_e2e.py` **executa o `twin_autopilot_check` de produção, original e patcheado, com banco de teste**, usando os guardas reais enviados e stubs só para os 4 módulos que não recebi (`twin_policy`, `twin_output_guard`, `owner_audio_dependencies` e a assinatura de produção do `twin_risk_gate`): o **original** envia a pergunta de saúde devolvida, o "Pode emitir" e o "👋" a um robô (controles negativos com código real); o patcheado, não. O teste de patcher: aborta se o original não for o esperado ou se uma âncora não for única; **o `darius_twin.py` ORIGINAL de produção reproduz o bug** (controle negativo com código real) e o patcheado o corrige; controles: contato doente recebe a pergunta, nome do contato é preservado, interruptor desliga; o `handlers.py` patcheado só difere em 3 linhas. Limite: os 4 stubs podem divergir do comportamento real desses módulos.

## Aplicação (futura, só com seu aval)
Mesmo padrão das anteriores: conferir hashes dos arquivos DENTRO do container, copiar para nomes temporários, backup dentro do container, trocar, reiniciar, verificar, voltar sozinho se falhar; rollback = recolocar os originais. **Atenção:** um `docker cp` se perde se o container for recriado.
