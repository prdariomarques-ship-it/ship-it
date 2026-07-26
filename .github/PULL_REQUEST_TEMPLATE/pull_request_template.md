## Capability ID

<!-- Exemplo: CAP-001, CAP-002, DEBT-001, ARCH-001 -->

## Summary

_Descreva em 2-3 frases o que este PR faz e por quê._

## Related Issues

<!-- Exemplo: Closes #11, Fixes #12, Relates to #13 -->

## Files Changed

_Descreva os arquivos modificados e o motivo de cada mudança:_

| Arquivo | Descrição da Mudança |
|---------|---------------------|
| _caminho/arquivo.py_ | _descrição_ |

## Tests Executed

<!-- Liste os testes que foram executados para validar esta mudança -->

- [ ] Backend: `pytest` (todos os testes passando)
- [ ] Frontend: `npm test` (todos os testes passando)
- [ ] Frontend E2E: `npm run e2e` (se aplicável)
- [ ] Lint: `ruff check .` / `npm run lint` (sem erros)
- [ ] Type check: `mypy` / `tsc` (sem erros)
- [ ] Migrations: `alembic upgrade head` + `alembic downgrade base`

## Evidence

<!-- Cole screenshots, logs de testes, ou links para evidências de que a mudança funciona -->

## CI Status

- [ ] Todos os checks de CI estão verdes
- [ ] Security scan limpo
- [ ] Dependency audit limpo

## Checklist

- [ ] Código segue os padrões do projeto (Ruff, ESLint)
- [ ] Testes cobrem o caminho feliz e casos de erro
- [ ] Nenhuma lógica não relacionada foi modificada
- [ ] Secrets ou credenciais não foram commitados
- [ ] Migration testada com rollback

## Documentation Updated

- [ ] `README.md` atualizado (se aplicável)
- [ ] `docs/` atualizado (se aplicável)
- [ ] Docstrings atualizadas (se aplicável)

## Breaking Changes

- [ ] Sim
- [ ] Não

_Se sim, descreva:_

## Rollback Plan

_Descreva como reverter esta mudança em caso de problema em produção:_

1. _Passo 1_
2. _Passo 2_

---

## Reviewer Notes

<!-- Informações adicionais para o reviewer: contexto, decisões, trade-offs -->
