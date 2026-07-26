# GitHub Engineering Workflow — OSAI

Este documento descreve o workflow de engenharia utilizado no repositório OSAI
(`prdariomarques-ship-it/ship-it`). Ele define como Issues, Projects, Pull Requests
e CI/CD se integram para garantir que o desenvolvimento seja rastreável,
reproduzível e auditável.

---

## 1. Visão Geral do Fluxo

O fluxo de trabalho segue a sequência abaixo, onde cada etapa é rastreável
no GitHub:

```
Issue → Label → Milestone → Project → Pull Request → CI → Merge
```

A **Issue** é o contrato de trabalho. A conversa não é a referência principal;
o GitHub é a fonte oficial do estado do projeto.

---

## 2. Issue Lifecycle

### 2.1 Criação de Issues

Toda Issue deve ser criada a partir de um template oficial:

| Template | Uso |
|----------|-----|
| **Capability** | Nova capability de produto (CAP-XXX) |
| **Bug Report** | Comportamento incorreto ou regressão |
| **Architecture Improvement** | Mudança estrutural no sistema (ARCH-XXX) |
| **Technical Debt** | Atalho conhecido que precisa ser revisado (DEBT-XXX) |
| **Performance Improvement** | Otimização de latência, throughput ou recursos (PERF-XXX) |
| **Security Issue** | Vulnerabilidade ou falha de segurança (SEC-XXX) |

### 2.2 Estrutura Obrigatória de uma Capability Issue

Toda Capability Issue deve conter obrigatoriamente:

| Seção | Descrição |
|-------|-----------|
| **Capability ID** | Código único (CAP-001, CAP-002, etc.) |
| **Objective** | Objetivo da capability em 1-2 frases |
| **Business Value** | Valor de negócio e problema resolvido |
| **Acceptance Criteria** | Critérios verificáveis para considerar a Issue completa |
| **Definition of Done** | Condições finais (código, testes, docs, PR aprovado) |
| **Dependencies** | Dependências externas ou internas |
| **Priority** | P0 (Critical) a P3 (Low) |
| **Release** | release-1.1, release-1.2 |
| **Area** | frontend, backend, fullstack, infrastructure, ai, devops |
| **AI Owner** | Modelo/agente responsável pela implementação |

### 2.3 Padronização de Títulos

Todos os títulos seguem o padrão:

```
<Prefix>-XXX - <Short Description>
```

Onde `<Prefix>` é:

| Prefixo | Significado |
|---------|-------------|
| `CAP` | Capability de produto |
| `BUG` | Bug Report |
| `ARCH` | Architecture Improvement |
| `DEBT` | Technical Debt |
| `PERF` | Performance Improvement |
| `SEC` | Security Issue |

### 2.4 Labels

As Labels são categorizadas em 5 dimensões:

**Prioridade:**

| Label | Significado | Cor |
|-------|-------------|-----|
| `P0` | Critical — resolve imediatamente | Vermelho |
| `P1` | High — sprint atual | Laranja |
| `P2` | Medium — próximo sprint | Amarelo |
| `P3` | Low — backlog | Azul |

**Tipo:**

| Label | Significado |
|-------|-------------|
| `feature` | Nova funcionalidade |
| `bug` | Comportamento incorreto |
| `enhancement` | Melhoria de funcionalidade existente |
| `architecture` | Mudança arquitetural |
| `performance` | Otimização de performance |
| `security` | Questão de segurança |
| `refactor` | Refatoração sem mudança de comportamento |
| `documentation` | Atualização de documentação |

**Área:**

| Label | Significado |
|-------|-------------|
| `frontend` | Trabalho no frontend/UI |
| `backend` | Trabalho no backend/server |
| `fullstack` | Trabalho que afeta ambas as camadas |
| `infrastructure` | Infraestrutura, deploy, infraestrutura como código |
| `ai` | Agentes, providers de LLM, Cognitive Pipeline |
| `devops` | CI/CD, automação, monitoramento |

**Release:**

| Label | Significado |
|-------|-------------|
| `release-1.1` | Target release para OSAI v1.1 |
| `release-1.2` | Target release para OSAI v1.2 |

**Status:**

| Label | Significado |
|-------|-------------|
| `blocked` | Bloqueada por dependência externa |
| `ready` | Pronta para ser trabalhada |
| `in-progress` | Em andamento |
| `review` | Em code review |
| `done` | Concluída |

### 2.5 Milestones

Milestones agrupam Issues por release:

| Milestone | Descrição |
|-----------|-----------|
| **Release 1.1** | Capabilities iniciais: Economic Calendar, Market News Feed, Real-Time Market Data, Alerts Center, Client Workspace |
| **Release 1.2** | Capabilities de evolução planejadas |

---

## 3. Project Lifecycle

O GitHub Project **"OSAI Release 1.1"** é o quadro Kanban principal do projeto.

### 3.1 Colunas

| Coluna | Descrição | WIP Limit |
|--------|-----------|-----------|
| 📥 **Product Backlog** | Issues priorizadas aguardando início | 5 |
| 🎯 **Ready** | Issues prontas para serem trabalhadas | — |
| ⚙️ **In Development** | Issues em implementação ativa | 3 |
| 🧪 **CI Validation** | Issues em validação de CI/CD | 5 |
| 👀 **Code Review** | Issues aguardando revisão | — |
| 🚀 **Ready to Merge** | Issues aprovadas, prontas para merge | — |
| ✅ **Done** | Issues concluídas e merged | — |
| 🏛 **Architecture Backlog** | Issues arquiteturais (separado do Product Backlog) | — |

### 3.2 Governança de Colunas

- **Product Backlog** e **Architecture Backlog** são completamente separados.
- Trabalho de engenharia (infraestrutura, débito técnico, segurança) nunca
  é misturado com trabalho de produto.
- Uma Issue só avança de coluna quando todos os critérios da coluna anterior
  estão satisfeitos.

### 3.3 Movimentação de Issues

| De | Para | Gatilho |
|----|------|---------|
| Product Backlog | Ready | Issue revisada, labels definidas, dependências resolvidas |
| Ready | In Development | PR criado, branch vinculada à Issue |
| In Development | CI Validation | CI verde em todos os checks |
| CI Validation | Code Review | PR submetido para revisão |
| Code Review | Ready to Merge | Review aprovado |
| Ready to Merge | Done | Merge realizado |

---

## 4. PR Lifecycle

### 4.1 Regras de Pull Request

1. Todo PR deve referenciar uma Issue via `Closes #XXX` ou `Fixes #XXX`.
2. O PR deve usar o template oficial (`.github/PULL_REQUEST_TEMPLATE/`).
3. O PR deve conter:
   - Capability ID
   - Resumo da mudança
   - Arquivos modificados e motivo
   - Testes executados
   - Evidências (screenshots, logs)
   - Status de CI
   - Checklist de qualidade
   - Documentação atualizada
   - Breaking Changes (se aplicável)
   - Rollback Plan

### 4.2 Regras de Merge

- Merge sempre via **squash** para manter histórico linear.
- Branch fonte deve estar atualizada com `master`.
- Todos os checks de CI devem estar verdes.
- Pelo menos 1 review aprovado (se Branch Protection estiver configurada).

---

## 5. CI Lifecycle

O pipeline de CI é definido em `.github/workflows/ci.yml` e executa:

### 5.1 Backend

| Step | Ferramenta | Nota |
|------|-----------|------|
| Install | `pip install -r requirements-dev.txt` | Python 3.12 |
| Lint | `ruff check .` | Erro se falhar |
| Type check | `mypy --ignore-missing-imports .` | Erro se falhar |
| Format | `ruff format --check .` | Warning (código não reformulado) |
| Security | `pip-audit -r requirements.txt` | Warning (report only) |
| Tests | `pytest -q` | Erro se falhar |
| Migrations | `alembic upgrade head` + `downgrade base` | Valida rollback |

### 5.2 Frontend

| Step | Ferramenta | Nota |
|------|-----------|------|
| Install | `npm ci` | Node.js 20 |
| Lint | `npm run lint` | Erro se falhar |
| Security | `npm audit --audit-level=high` | Warning (report only) |
| Tests | `npm run test` | Erro se falhar |
| Build | `npm run build` | Erro se falhar (inclui tsc) |

### 5.3 Docker

| Step | Ferramenta | Nota |
|------|-----------|------|
| Validate | `docker compose config -q` | Valida configuração |

---

## 6. Release Lifecycle

### 6.1 Estratégia de Branches

| Branch | Descrição |
|--------|-----------|
| `master` | Branch principal, sempre estável e deployável |
| `feature/*` | Branches de desenvolvimento de capabilities |
| `fix/*` | Branches de correção de bugs |
| `release/*` | Branches de preparação de release |

### 6.2 Processo de Release

1. Todos os Issues do Milestone estão em `Done`.
2. CI verde na branch `master`.
3. Tag semântica criada (`v1.1.0`, `v1.2.0`).
4. Release Notes geradas a partir das Issues do Milestone.
5. Deploy em produção.

### 6.3 Versionamento Semântico

O projeto segue [Semantic Versioning](https://semver.org/):

- **MAJOR**: Mudanças incompatíveis com versões anteriores.
- **MINOR**: Novas funcionalidades compatíveis.
- **PATCH**: Correções de bugs compatíveis.

---

## 7. Branch Protection

A configuração recomendada para `master` inclui:

- [ ] Exigir Pull Requests antes do merge
- [ ] Exigir CI bem-sucedido
- [ ] Bloquear pushes diretos
- [ ] Exigir resolução de conversas
- [ ] Exigir branches atualizadas antes do merge
- [ ] Histórico linear (squash merge)

> **Nota**: Esta configuração requer permissões de admin. Se não disponível,
> consulte o checklist manual em `docs/BRANCH_PROTECTION_CHECKLIST.md`.

---

## 8. Code Review Policy

### 8.1 Critérios de Review

O reviewer deve verificar:

1. Código segue padrões de estilo (Ruff/ESLint limpo).
2. Testes cobrem caminhos felizes e de erro.
3. Nenhuma lógica não relacionada foi modificada.
4. Secrets não foram commitados.
5. Migrations funcionam com rollback.
6. Documentação foi atualizada.

### 8.2 Feedback

- Comentários devem ser específicos e acionáveis.
- Sugestões de melhoria são bem-vindas, mas não devem bloquear o merge
  se não forem críticas.

---

## 9. Definition of Done

Uma Issue só é considerada **Done** quando:

| Critério | Verificação |
|----------|-------------|
| Código implementado | PR merged |
| Testes passando | CI verde |
| Documentação atualizada | README, docstrings, docs/ |
| Pull Request aprovado | Code review completo |
| Status atualizado | GitHub Project movido para "Done" |
| Labels atualizadas | `done` aplicada, outras removidas |
| Milestone confirmado | Issue aparece como fechada no Milestone |

---

## 10. Engenharia vs. Produto

O repositório separa claramente:

| Categoria | Coluna/Label | Descrição |
|-----------|-------------|-----------|
| Product Backlog | 📥 Product Backlog | Capabilities de produto (CAP-XXX) |
| Architecture Backlog | 🏛 Architecture Backlog | Mudanças arquiteturais (ARCH-XXX) |
| Technical Debt | `technical-debt` | Atalhos conhecidos (DEBT-XXX) |
| Security | `security` | Questões de segurança (SEC-XXX) |
| Performance | `performance` | Otimizações (PERF-XXX) |
| Capabilities | `feature` | Novas funcionalidades |
| Releases | Milestones | Release 1.1, Release 1.2 |

Nenhum trabalho de engenharia deve ser misturado com trabalho de produto.
