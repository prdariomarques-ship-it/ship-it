# Registro de riscos

| ID | Risco | Gravidade | Evidência | Responsável | Próxima ação |
|---|---|---|---|---|---|
| R1 | Leitura de resumo com fato reatribuído (H1). | Alta | Revisão formal; testes de H1 reprovavam antes da correção. | Implementação | Revisão independente da correção. |
| R2 | Reconciliação concorrente (M1, M2) e leitura com escrita (M4). | Média | Revisão formal; testes de regressão. | Implementação | Revisão independente. |
| R3 | Tabela de eventos sem retenção; consulta cresce com o histórico (M3 e M5). | Média | Revisão formal. | Responsável do projeto | Adiado por decisão do responsável. |
| R4 | Texto retratado permanece no histórico de revisões (M5). | Média | Revisão formal. | Responsável do projeto | Adiado. |
| R5 | Marca persistida pode ficar atrás de mensagens já cobertas. | Média | Teste determinístico falha na baseline. | Responsável do projeto | Fora de escopo nesta rodada. |
| R6 | Conteúdo não confiável (D7): saída de ferramenta e bloco de estilo sem fronteira. | Alta | Testes de D7. | Responsável do projeto | Pendente. |
| R7 | D8 (fallback do sumarizador) e D9 (outbox vetorial) não implementados. | Alta | Auditoria de fechamento. | Responsável do projeto | Pendente. |
| R8 | Concorrência validada só em uma máquina. | Média | Auditoria de fechamento. | Responsável do projeto | Plano de multi-host pendente. |
| R9 | Fidelidade semântica do modelo de sumarização não aprovada. | Alta | Rodadas de avaliação. | Sessão de modelos e GPU | Decisão do responsável sobre modelo. |
| R10 | Rodada de modelos retomada sem autorização confirmada, usando a GPU. | Média | Verificação de contêiner e GPU. | Responsável do projeto | Confirmar autorização. |
| R11 | Linha canônica (`984b012`, `36488bb`) não aparece no GitHub público. | Alta | Consulta à API pública (HTTP 422). | Responsável do projeto | Confirmar se o remoto oficial é outro. |
| R12 | Repositório público: publicar detalhe operacional expõe o projeto. | Média | Consulta de visibilidade. | Responsável do projeto | Decidir sobre publicação e destino privado. |
