# Responsáveis por recursos

Quem pode usar cada recurso. Quando não houver responsável, o recurso não deve ser tocado.

| Recurso | Responsável | Estado | Regra |
|---|---|---|---|
| GPU | Sessão de modelos e GPU | Em uso intenso (≈ 10 GiB de 12 GiB de VRAM) [verificado] | Só a sessão responsável; não iniciar Ollama ou inferência em paralelo. |
| Ollama e contêiner de inferência | Sessão de modelos e GPU | Ativo [verificado] | Não reiniciar durante uma execução. |
| Contêineres de teste (PostgreSQL 16 e backend) | Sessão de implementação | Descartáveis; nenhum restante desta sessão [verificado] | Só remover os próprios, pelo rótulo. |
| Cópia `candidate-agent-memory-ledger-v1` | Ninguém (baseline) | Somente leitura | Não escrever sem nova autorização. |
| Cópia `candidate-agent-reconciliation-H1-M1-M2-M4` | Sessão de implementação | Única escritora | Outras sessões só leem. |
| Repositório público no GitHub | Responsável do projeto | Público; branch padrão `master` | Sem push de histórico local não autorizado. |
