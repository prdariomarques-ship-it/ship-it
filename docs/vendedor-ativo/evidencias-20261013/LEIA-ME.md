# Evidências de execução (13/10/2026)

Resultados **do autor**, obtidos num PostgreSQL 16 descartável local (iniciado e apagado dentro da sessão). Não há GitHub Actions
para estes commits e nada aqui foi executado na instalação do titular nem em produção.

| Arquivo | O que é |
|---|---|
| `pytest-backend-com-postgres.txt` | `backend/tests` completo com `TEST_POSTGRES_URL` definida (os testes PG rodam, não ficam pulados) |
| `pytest-whatsapp-agents-fix-com-postgres.txt` | pacote do PR #63 com `WHATSAPP_DEDUP_PG_ADMIN_URL` (precisa de `psycopg` no ambiente de teste) |
| `ruff-mypy.txt` | `ruff` limpo; `mypy` com os mesmos 12 erros que já existiam antes desta branch |
| `mutantes.txt` | testes de mutação da correção do fechamento de reserva comum (Z01–Z08) |

Mutantes Z01–Z06 são **seis**, todos mortos. A frase "6 dos 7" da mensagem anterior misturou o número de testes novos de worker (7)
com o de mutantes: não existe sétimo mutante e nenhum dos seis sobreviveu. Z07 e Z08 foram acrescentados depois, a pedido do parecer
(ver `mutantes.txt`).

## Reconciliação dos cinco erros de mypy e guarda anti-skip (13/10, depois do `794209c`)

Resultados do autor, no mesmo tipo de PostgreSQL 16 descartável com senha na porta 5432 (simulação das variáveis do CI, **não** é
GitHub Actions). Os logs `reconciliacao-*.txt` foram gerados sobre a árvore com os dois commits (reconciliação + guarda); o campo de
SHA que eles imprimem mostra o HEAD de antes dos commits, porque a execução foi feita com a árvore ainda sem commit.

| Arquivo | O que é |
|---|---|
| `historico-sha256.txt` | SHA-256 das sete revisões históricas copiadas byte a byte do pacote `aftercare-review` (conferido contra os arquivos do repositório) |
| `reconciliacao-ruff-mypy.txt` | `ruff` limpo; `mypy --ignore-missing-imports .` (como no CI) sem erros; `mypy .` sem a opção ainda acusa 7 módulos/stubs ausentes (listados) |
| `reconciliacao-pytest-backend.txt` | `python -m pytest -q -rs -p ci_require_postgres` com `REQUIRE_POSTGRES_TESTS=1`: 1689 passaram, nenhum pulado |
| `reconciliacao-pytest-pacote.txt` | `whatsapp_agents_fix/` com a guarda ligada: 153 passaram |
| `reconciliacao-alembic-sqlite.txt` | `alembic upgrade head` / `downgrade base` em SQLite (passo de migrações do CI) |
| `mutantes-reconciliacao-R01-R17.txt` | 17 mutantes dos testes novos (áudio, catálogo, marcador, migrações), todos mortos |
| `mutantes-guarda-anti-skip-G01-G05.txt` | 5 mutantes da guarda anti-skip, todos mortos |
