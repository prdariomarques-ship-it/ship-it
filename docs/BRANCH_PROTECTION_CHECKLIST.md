# Branch Protection Checklist — OSAI

Este documento contém o checklist manual para configurar Branch Protection
na branch `master` do repositório `prdariomarques-ship-it/ship-it`.

---

## Configuração Manual

Acesse: **Settings → Branches → Branch protection rules → Add branch protection rule**

Branch name pattern: `master`

### Proteções Obrigatórias

- [ ] **Require a pull request before merging**
  - [ ] Require approvals: **1** (mínimo)
  - [ ] Dismiss stale pull request approvals when new commits are pushed
  - [ ] Require review from Code Owners (se CODEOWNERS existir)

- [ ] **Require status checks to pass before merging**
  - [ ] CI
  - [ ] All required checks must pass

- [ ] **Do not allow bypassing the above settings**

- [ ] **Require branches to be up to date before merging**

- [ ] **Require conversation resolution before merging**

- [ ] **Require linear history** (squash merge)

### Proteções Adicionais (Recomendadas)

- [ ] **Restrict who can push to matching branches**: apenas mantenedores
- [ ] **Require signed commits** (se GPG estiver configurado)
- [ ] **Include administrators** (para garantir que até admins passam pelo processo)

### Merge Strategy

- [ ] **Allow squash merging** (recomendado — mantém histórico linear)
- [ ] Disallow merge commits
- [ ] Disallow rebase merging

---

## Justificativa

Cada proteção garante que:

| Proteção | Justificativa |
|----------|---------------|
| PR obrigatório | Revisão de código antes do merge |
| CI obrigatório | Código testado antes de entrar na branch principal |
| Approvals | Qualidade garantida por revisão humana |
| Branches atualizadas | Evita conflitos silenciosos |
| Conversação resolvida | Nenhum comentário fica sem resposta |
| Histórico linear | Histórico limpo e auditável |
| Squash merge | Commits agrupados por feature, não por commit individual |
