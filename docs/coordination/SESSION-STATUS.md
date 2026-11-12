# Estado das sessões

Atualizado em 2026-11-12, por volta de 14:30 (horário de São Paulo). Fonte de cada linha indicada entre colchetes.

| Sessão | Tarefa | Diretório | Estado | Responsável | Próxima entrega |
|---|---|---|---|---|---|
| Implementação (H1/M1/M2/M4) | Correções na cópia de reconciliação | cópia `candidate-agent-reconciliation-H1-M1-M2-M4` | **COMPLETED na implementação; validação com pendência de relatório** [relatado + executado] | Sessão de implementação | Relatório final e manifesto |
| Revisão independente | Revisão somente leitura | nenhum (leitura) | **WAITING** [relatado] | Sessão de revisão | Parecer sobre H1/M1/M2/M4 após o diff |
| Modelos e GPU | Rodada de seleção de modelos | ambiente próprio | **IN PROGRESS** [verificado: contêiner de inferência ativo, uso de GPU alto] | Sessão MarquesColor | Resultados por modelo |

## Detalhamento
- **Implementação:** patches H1, M1, M2 e M4 aplicados na cópia; suíte completa da cópia concluída. Não há relatório final nem manifesto final ainda. [relatado pela sessão; resultado de junit conferido pela coordenação]
- **Revisão:** a revisão formal da etapa 1 foi entregue antes (achado H1 de alta severidade). Aguarda o diff completo das correções. [relatado]
- **Modelos e GPU:** a rodada foi interrompida e retomada depois; o contêiner de inferência está ativo. [verificado por consulta a contêineres e GPU]; autorização para essa retomada **não confirmada** pelo responsável do projeto.

## Cópias
- `candidate-agent-memory-ledger-v1`: baseline, somente leitura.
- `candidate-agent-reconciliation-H1-M1-M2-M4`: única escritora, sessão de implementação.
- r2 original, dot-fixes original, linha canônica: intocáveis.
