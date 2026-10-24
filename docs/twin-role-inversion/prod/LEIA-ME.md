# Patch de PRODUÇÃO (não aplicado) — papéis do Gêmeo

Arquivos reais recebidos em 24/10/2026 (cópias fiéis em `originais/`): `darius_twin.py` sha256 `c935113114ac5a71…` e `handlers.py` sha256 `ec6dd50c23ffae3d…`.

## O que muda (mínimo e aditivo)
- `darius_twin.py` (4 edições ancoradas): importa `agents/darius_twin_roles.py`; a regra de papéis vai ao fim do prompt; a linha do contato diz "NÃO é o Dário"; a resposta passa por `guard_role_inversion` (tira apelido do dono usado como vocativo e a pergunta de saúde devolvida; se sobrar nada, `TwinReplyUnavailable`, que o handler de produção já trata).
- `handlers.py` (2 edições): um `import` e a linha do histórico (447) passa a `build_twin_history(...)`, que acrescenta `[Dário]`/`[Gêmeo]` às saídas cuja autoria é conhecida (autopiloto vence `sent_by_human`; sem origem registrada fica como era).
- **Arquivo novo:** `backend/agents/darius_twin_roles.py` (só depende de `models.message` e `providers.llm.base`, que produção tem). Interruptor por ambiente: `TWIN_ROLE_GUARD_ENABLED=false`.

## O que NÃO entra, de propósito
Silêncio, robô, dinheiro, compromisso: produção tem `twin_policy`, `twin_autoreply_gate`, `twin_finance_guard`, `twin_commitment_guard`. Preciso ver esses módulos e os `.md` do prompt para testar com os casos reais se já cobrem, antes de qualquer outra mudança.

## Como foi verificado (sem VPS)
`python3 aplicar_twin_roles.py --origem originais --saida SAIDA` gera os dois arquivos (hashes fixados no teste `tests/test_twin_prod_patch.py`). O teste: aborta se o original não for o esperado ou se uma âncora não for única; **o `darius_twin.py` ORIGINAL de produção reproduz o bug** (controle negativo com código real) e o patcheado o corrige; controles: contato doente recebe a pergunta, nome do contato é preservado, interruptor desliga; o `handlers.py` patcheado só difere em 3 linhas. **Não executei** `twin_autopilot_check` de produção (depende de módulos que não tenho).

## Aplicação (futura, só com seu aval)
Mesmo padrão das anteriores: conferir hashes dos arquivos DENTRO do container, copiar para nomes temporários, backup dentro do container, trocar, reiniciar, verificar, voltar sozinho se falhar; rollback = recolocar os originais. **Atenção:** um `docker cp` se perde se o container for recriado.
