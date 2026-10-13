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
