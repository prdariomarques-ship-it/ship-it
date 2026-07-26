# Release Process — OSAI

Este documento descreve o processo de release do OSAI.

---

## 1. Visão Geral

O OSAI segue um processo de release baseado em milestones do GitHub,
versionamento semântico e deploy contínuo a partir da branch `master`.

---

## 2. Pré-requisitos para Release

Antes de criar uma release, verifique:

- [ ] Todas as Issues do Milestone estão com status **Done** no GitHub Project
- [ ] CI verde na branch `master`
- [ ] Nenhum PR pendente com merge necessário
- [ ] Documentação atualizada (`docs/`, `README.md`, Release Notes)
- [ ] Migrations testadas (upgrade e downgrade)
- [ ] Security scan limpo (`pip-audit`, `npm audit`)
- [ ] Performance baseline documentada (se aplicável)

---

## 3. Estratégia de Branches

| Branch | Descrição |
|--------|-----------|
| `master` | Branch principal, sempre estável e deployável |
| `feature/*` | Desenvolvimento de capabilities |
| `fix/*` | Correções de bugs |
| `release/*` | Preparação de release (opcional para hotfixes) |

---

## 4. Versionamento Semântico

O projeto segue [Semantic Versioning](https://semver.org/):

```
vMAJOR.MINOR.PATCH
```

| Componente | Quando incrementar |
|------------|-------------------|
| **MAJOR** | Mudanças incompatíveis com versões anteriores |
| **MINOR** | Novas funcionalidades compatíveis |
| **PATCH** | Correções de bugs compatíveis |

---

## 5. Processo de Release

### 5.1 Preparação

1. Confirme que todas as Issues do Milestone estão **Done**.
2. Atualize `RELEASE_NOTES.md` com as mudanças.
3. Atualize `VERSION_HISTORY.md` com a nova versão.
4. Execute a suite completa de testes:

```bash
cd backend && pytest -q && ruff check . && mypy --ignore-missing-imports .
cd frontend && npm test && npm run lint && npm run build
```

### 5.2 Tag e Release

1. Merge todas as branches de feature na `master`.
2. Crie a tag:

```bash
git tag -a v1.1.0 -m "Release 1.1.0 - Economic Calendar, Market News Feed, Real-Time Market Data, Alerts Center, Client Workspace"
git push origin v1.1.0
```

3. Crie a Release no GitHub:
   - Título: `v1.1.0`
   - Descrição: copiar das Release Notes
   - Tag: `v1.1.0`

### 5.3 Deploy

1. CI na branch `master` valida o deploy.
2. Execute o pipeline de deploy (conforme `RUNBOOK.md`).
3. Valide em produção (smoke tests).

### 5.4 Pós-Release

1. Atualize o Milestone para **Closed** no GitHub.
2. Mova Issues remanescentes para o próximo Milestone.
3. Escreva o `POST_RELEASE_REVIEW.md`.
4. Limpe branches de feature merged.

---

## 6. Hotfix

Para correções urgentes em produção:

1. Crie branch a partir da tag da release:

```bash
git checkout -b fix/urgent v1.1.0
```

2. Implemente a correção.
3. Abra PR e obtenha approval urgente.
4. Merge na `master`.
5. Crie tag patch: `v1.1.1`.

---

## 7. Rollback

Se o deploy causar problemas:

1. Reverta o deploy (conforme `RUNBOOK.md`).
2. Crie Issue `BUG-XXX` com `P0` priority.
3. Implemente correção via hotfix.
4. Deploy novamente.

---

## 8. Release Notes

As Release Notes seguem este formato:

```markdown
# v1.1.0

## New Capabilities
- CAP-001: Economic Calendar
- CAP-002: Market News Feed
- CAP-003: Real-Time Market Data
- CAP-004: Alerts Center
- CAP-005: Client Workspace

## Bug Fixes
- BUG-001: Fix timezone display in calendar

## Performance
- Reduced API response time by 40%

## Security
- Updated dependency X to patch CVE-2026-XXXX

## Breaking Changes
- None
```
