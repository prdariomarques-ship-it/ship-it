# Branch Protection Checklist — OSAI

> **STATUS: CONFIGURADO VIA API em 2026-07-26**
>
> Todas as proteções listadas abaixo foram aplicadas com sucesso via GitHub API.
> Este documento serve como referência de auditoria.

---

## Configuração Aplicada

**Branch**: `master`
**Método**: GitHub REST API (`PUT /repos/{owner}/{repo}/branches/{branch}/protection`)
**Data**: 2026-07-26

### Proteções Ativas

| Proteção | Status | Configuração |
|----------|--------|-------------|
| **Require status checks to pass** | Ativado | CI (strict mode) |
| **Require branches to be up to date** | Ativado | Branches devem estar atualizadas |
| **Require pull request reviews** | Ativado | 1 approval, dismiss stale reviews |
| **Require code owner reviews** | Ativado | CODEOWNERS obrigatório |
| **Require last push approval** | Ativado | Re-aprovação após novos commits |
| **Require conversation resolution** | Ativado | Todos comentários resolvidos |
| **Require linear history** | Ativado | Squash merge obrigatório |
| **Enforce for admins** | Ativado | Admins também seguem as regras |
| **Allow force pushes** | Desativado | Força desativada |
| **Allow deletions** | Desativado | Deleção desativada |
| **Block branch creation** | Desativado | Libera criação de novas branches |

### Merge Strategy

| Configuração | Status |
|-------------|--------|
| **Squash merge** | Ativado (padrão) |
| **Merge commit** | Desativado |
| **Rebase merge** | Desativado |
| **Auto merge** | Ativado |
| **Delete branch on merge** | Ativado |
| **Update branch** | Ativado |
| **Squash PR title as default** | Ativado |
| **Squash commit message from PR body** | Ativado |

---

## Verificação

Para verificar a configuração atual:

```bash
gh api repos/prdariomarques-ship-it/ship-it/branches/master/protection
```

Ou via interface: **Settings → Branches → Branch protection rules → master**

---

## Histórico

| Data | Ação | Método |
|------|------|--------|
| 2026-07-26 | Branch Protection aplicada | GitHub REST API |
| 2026-07-26 | Merge strategy configurada | GitHub REST API |
