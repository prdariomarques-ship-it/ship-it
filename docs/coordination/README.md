# Coordenação de sessões — Ship-It / Dario OS

Registro de engenharia da frente de **memória cumulativa** (ledger), da avaliação de modelos de sumarização e da frente MarquesColor POS Pro.

**Estado oficial:** `SHIP-IT: INTEGRATION HOLD / PRODUCTION NO-GO`. Nada aqui autoriza merge, integração, deploy ou alteração de produção.

## Como ler
| Arquivo | Conteúdo |
|---|---|
| `SESSION-STATUS.md` | Estado atual das sessões (último registro conhecido). |
| `SESSION-LOG.md` | Histórico cronológico, somente append. |
| `DECISION-LOG.md` | Decisões do responsável, com escopo de autorização. |
| `TEST-RESULTS.md` | Resultados de suítes e comparação por identificador. |
| `ARTIFACT-INDEX.md` | Índice de relatórios, manifestos e diffs (referências locais). |
| `RISK-REGISTER.md` | Riscos abertos. |
| `RESOURCE-OWNERSHIP.md` | Quem usa GPU, Ollama, Docker, bancos e cópias de trabalho. |

## Regras
1. Um único escritor por cópia de código.
2. Relato de outra sessão é marcado como **relatado**; só é **verificado** quando há execução ou leitura de evidência nesta coordenação.
3. Resultado negativo é preservado. Correção de registro é um novo registro que aponta o anterior.
4. Nenhum dado sensível, caminho pessoal, credencial ou dump entra neste repositório. Evidências completas ficam fora do repositório, em armazenamento local.
5. Commits desta área são só de documentação. Não há PR nem merge automáticos.

## Sessões
- **Implementação** (cópia de reconciliação): corrige H1, M1, M2 e M4.
- **Revisão independente**: somente leitura.
- **Modelos e GPU**: avaliação de modelos de sumarização; dona exclusiva da GPU e do Ollama.
