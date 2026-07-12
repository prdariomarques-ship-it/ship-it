# ENGINEERING_PROCESS_v2.md

**Manual Oficial de Processo de Engenharia — Plataforma Dario**

Documento único, definitivo, consolidado. Versão 2.0 — Incorpora 11 Princípios Obrigatórios, 
4 Gates Críticos, 8-State Machine, lições da falha VULN-1A.

**Autoridade**: Tech Lead da Plataforma Dario  
**Escopo**: Todas as Sprints v1.2.1+  
**Efetiva em**: Pós-aprovação pelo Chief Architect  
**Status**: Proposta (sem commit, sem push)

---

## 1. Objetivo do Processo

Estabelecer uma única fonte de verdade para engenharia da Plataforma Dario que:

- **Reduce risk** através de gates obrigatórios, validações em 3 camadas, e proof artifacts
- **Eliminate ambiguity** com 8-state machine linear, checklists executáveis, responsabilidades claras
- **Prevent recurrence** de falhas através de RCA formal, principles enforcement, e processo gatekeeping
- **Enable speed** através de definições claras (DoR, DoD), workflows sem bloqueadores não-documentados
- **Scale governance** através de role-based checklists que crescem com o time, sem perder qualidade

Processo **não é burocracia**: é proteção da qualidade através de validações que poupam retrabalho.

---

## 2. Papéis Oficiais

Cada papel tem responsabilidades explícitas, pontos de decision, e escalação clara.

### 2.1 Chief Architect

**Responsabilidade**: Integridade arquitetural, decisões de longo prazo, aprovação de releases.

**Decision Points** (só podem ser tomadas por CA):
- Aprovação de RFC (pedidos de mudança arquitetural)
- Aprovação de release para produção
- Escalação de falhas CRITICAL
- Mudanças em ARCHITECTURE_BASE.md ou ARCHITECTURE_DECISIONS.md
- Autorização de violação de Principles (rare, documentada)

**Disponibilidade SLA**:
- RFC review: 24 horas
- Release approval: 1 hora (durante trabalho)
- Incident escalation: 15 minutos

**Não participa em**: Code review linha a linha, planning de sprint, daily standup

### 2.2 Tech Lead

**Responsabilidade**: Governança operacional, gatekeeping de processo, tech debt tracking.

**Decision Points** (só podem ser tomadas por TL):
- Aprovação de Definition of Ready
- Transições de state (ANÁLISE → APROVADO, etc.)
- Aprovação de Code Review (4 gates validados)
- Autorização de hotfix
- Conducção de RCA
- Escalação para Chief Architect

**Disponibilidade SLA**:
- Code Review: 4 horas
- DoR approval: 4 horas
- Blocker resolution: 1 hora
- RCA: 24 horas post-incident

**Participa em**: Todos os gates, planning, code review, release approval, postmortem

### 2.3 Software Engineer

**Responsabilidade**: Implementação, testes, validação local, criação de PRs.

**Decision Points** (nenhuma — segue processo):
- Qual branch strategy usar (já definida)
- Qual test framework usar (já definida)
- Quando abrir PR (quando DoD começar a ser satisfeito)
- Quanto tempo gasta em task (auto-estimado, reportado em standup)

**Accountability**:
- Código passa em ruff/eslint/tsc/pytest antes de PR abrir
- Tests ≥ 70% coverage
- Commits têm mensagens descritivas
- Responde a CR feedback dentro de 4 horas
- Não violam Principles (ex: importar Core em módulo = failure)

**Participa em**: Implementation, local testing, PR creation, CR feedback loop, standup

### 2.4 Systems Analyst (QA/Infrastructure)

**Responsabilidade**: Testes E2E, smoke tests staging, deployment verification, incident response.

**Decision Points**:
- Qual critério de aceite testar manualmente (já em DoA)
- Quando um smoke test falha: hotfix ou rollback
- Qual métrica monitorar em produção (em coordenação com TL)

**Accountability**:
- E2E tests passam contra build de produção
- Smoke test em staging pré-release
- Post-deploy verification (health checks, logs, metrics)
- Escalação de falhas de infraestrutura

**Participa em**: Release validation, E2E testing, monitoring, incident response, postmortem

---

## 3. Capability Matrix

Matriz de "quem pode fazer o quê" de forma explícita. Elimina ambiguidade.

| Ação | Software Engineer | Tech Lead | Chief Architect | Systems Analyst |
|------|------------------|-----------|-----------------|-----------------|
| Escrever código | ✅ Sempre | ❌ Nunca | ❌ Nunca | ❌ Nunca |
| Criar branch | ✅ Sempre | ✅ Raro (RCA) | ❌ Nunca | ❌ Nunca |
| Abrir PR | ✅ Sempre | ✅ Raro | ❌ Nunca | ❌ Nunca |
| Fazer commit | ✅ Sempre | ✅ RCA/hotfix | ❌ Nunca | ❌ Nunca |
| Fazer push | ✅ Se aprovado | ✅ RCA/hotfix | ❌ Nunca | ❌ Nunca |
| Validar DoR | ❌ Nunca | ✅ Sempre | ❌ Nunca | ❌ Nunca |
| Validar Code Review | ❌ Nunca | ✅ Sempre (4 gates) | ⚠️ Raro (complex) | ❌ Nunca |
| Mesclar PR | ❌ Nunca | ✅ Sempre | ❌ Nunca | ❌ Nunca |
| Decidir release | ❌ Nunca | ⚠️ Staging | ✅ Produção | ✅ Executa |
| Conduzir RCA | ❌ Nunca | ✅ Sempre | ⚠️ CRITICAL | ❌ Nunca |
| Autorizar hotfix | ❌ Nunca | ✅ Sempre | ⚠️ Se CRITICAL | ❌ Nunca |
| Executar rollback | ❌ Nunca | ⚠️ Autoriza | ❌ Nunca | ✅ Sempre |

**Legenda**: ✅ = Permissão; ⚠️ = Exceção; ❌ = Proibido

---

## 4. Capability Gate

Validação obrigatória: "Pode este ambiente executar as tarefas desta Sprint?"

### 4.1 Declaração de Capacidades Oficiais

Executável declarado de forma explícita:

```
CAP_READ_FILES       = YES    (ler arquivos do repositório)
CAP_WRITE_FILES      = YES    (editar/criar arquivos no repositório)
CAP_GIT              = YES    (git clone, commit, push, etc.)
CAP_DOCKER           = NO     (daemon Docker não disponível)
CAP_NETWORK          = NO     (sem acesso HTTP/HTTPS outbound)
CAP_TEST_RUNTIME     = YES    (pytest, npm test executáveis)
CAP_BROWSER          = NO     (sem Chromium/Firefox interativo)
CAP_CI_PIPELINE      = YES    (GitHub Actions available)
CAP_COMPILE_PYTHON   = YES    (Python 3.12+, ruff, mypy)
CAP_COMPILE_NODEJS   = YES    (Node.js 20+, npm, tsc)
```

### 4.2 Implicações na Sprint

**O que PODE fazer nesta Sprint**:
- ✅ Mudanças em código Python/TypeScript
- ✅ Adicionar/modificar testes (pytest, vitest, playwright)
- ✅ Commits e PRs
- ✅ Linting, type checking, build

**O que NÃO PODE fazer**:
- ❌ Testar interativamente em browser local (CI só)
- ❌ Testar CSP com staging real HTTPS (infrastructure blocker)
- ❌ Testar integrações externas que exigem network real
- ❌ Docker local (reverter para docker compose config validation só)

### 4.3 Checklist Capability Gate (Software Engineer)

Executar ANTES de aceitar qualquer tarefa:

```bash
# 1. Python
python --version        # Expect: 3.12+
pip list | grep ruff    # Expect: ruff present
which pytest            # Expect: /path/to/pytest

# 2. Node.js
node --version          # Expect: 20+
npm --version           # Expect: 8+
which tsc               # Expect: /path/to/tsc

# 3. Git
git --version           # Expect: 2.35+
git config user.name    # Expect: configured

# 4. Verificar que Docker e Network NÃO estão disponíveis
docker ps 2>&1 | grep -q "Cannot connect"  # Expect: error
curl -I https://google.com 2>&1 | grep -q "Couldn't resolve host"  # Expect: error

# 5. Limpar diretório
git status              # Expect: "nothing to commit, working tree clean"
```

**Se algum check falha: NÃO aceite tarefa. Escalpe para Tech Lead.**

---

## 5. Working Tree Gate

Validação de estado do repositório **antes de começar qualquer tarefa**.

### 5.1 Pre-Task Checklist

```bash
# Passo 1: Repositório está limpo?
git status
# Esperado: "working tree clean"

# Passo 2: Qual é o último commit?
git log -1 --oneline
# Verify que é esperado (não um merge commit acidental)

# Passo 3: Remote está sincronizado?
git fetch origin
git status
# Esperado: "Your branch is up to date with 'origin/main'."

# Passo 4: Nenhum stash antigo deixado?
git stash list
# Esperado: empty, ou SÓ stashes com data recente
```

### 5.2 Estados Inválidos (Working Tree Gate FALHA)

Qualquer um destes invalida a Working Tree:

- ❌ Uncommitted changes (`git status` mostra M, A, D, etc.)
- ❌ Untracked files fora do esperado (`.pyc`, `__pycache__/`, `.env`)
- ❌ Branch ahead de remote (commits locais não pushados)
- ❌ Merge conflicts não resolvidos (se houver git rebase/merge em andamento)
- ❌ Stash antigo (> 24h) sem razão documentada

### 5.3 Remediação (Tech Lead Only)

Se encontrar Working Tree inválida:

1. **Investigar**: `git log --oneline -10` e `git status`
2. **Stash com mensagem**: `git stash save "MAINT: [razão investigada]"`
3. **Resetar**: `git reset --hard origin/main`
4. **Verificar**: `git status` limpo
5. **Documentar**: 1-2 parágrafos em RCA mínimo se for recorrente
6. **Comunicar**: Slack ao time

---

## 6. Definition of Ready

Checklist que DEVE ser verdade antes de item sair de ANÁLISE para APROVADO PARA IMPLEMENTAÇÃO.

### 6.1 Checklist DoR (Product Lead + Tech Lead)

- [ ] **Descrição clara**: 2-3 linhas máximo, não vago
- [ ] **Critérios de aceite**: 3-5 critérios verificáveis (não "funcionar bem")
- [ ] **Escopo definido**: Claro o que está DENTRO e FORA (explicitamente)
- [ ] **Bloqueadores documentados**: Se há dependência, listada e mitigada
- [ ] **Risco arquitetural**: Se toca fronteira, RFC ou CA aprovação
- [ ] **Estimativa**: T-shirt (XS, S, M, L, XL) preenchido
- [ ] **Referências linkadas**: Specs, ADRs, guias, links para código
- [ ] **Não é tech debt puro**: Se é refactoring, tem valor concreto documentado
- [ ] **Rollback plan**: 1-2 linhas descrevendo como desfazer
- [ ] **Plano de testes**: Quais testes devem passar (unit, E2E, manual)
- [ ] **Success metrics**: Como vamos medir que foi bem sucedido

### 6.2 Rejeição de DoR

Item volta a ANÁLISE se:

- Descrição vaga ("fix bug", "improve performance")
- Critérios de aceite não são verificáveis
- Bloqueadores não documentados
- Risco alto sem aprovação CA
- Nenhuma métrica de sucesso

**Responsável por rejeição**: Tech Lead. **Motivo documentado**: em comentário no backlog ou SPRINT_vX_PLAN.md.

---

## 7. Official Task State Machine

8 estados lineares obrigatórios. Transições unidirecionais (forward) ou retorno explícito a ANÁLISE.

### 7.1 Os 8 Estados

```
ANÁLISE
    ↓ [DoR aprovada]
APROVADO PARA IMPLEMENTAÇÃO
    ↓ [Work starts]
IMPLEMENTADO
    ↓ [4 Gates validadas]
VALIDADO
    ↓ [CR feedback incorporated]
CODE REVIEW APROVADO
    ↓ [TL sign-off]
READY FOR COMMIT
    ↓ [Push to main]
COMMIT
    ↓ [CI green]
MERGE
```

### 7.2 Descrição de Cada Estado

| Estado | O que significa | Quem controla | Artefato de saída | Próximo estado |
|--------|-----------------|---------------|------------------|----------------|
| **ANÁLISE** | Item no backlog, sem comprometimento. Pode retornar aqui. | Product Lead | DoR checklist | APROVADO |
| **APROVADO PARA IMPLEMENTAÇÃO** | Comprometimento feito. DoR passou. SW Eng pode começar. | Tech Lead | Approval comment em issue | IMPLEMENTADO |
| **IMPLEMENTADO** | Código escrito, testes adicionados. PR aberto. | Software Engineer | PR com tests | VALIDADO |
| **VALIDADO** | 4 Gates passadas (VPM, ACG, 3LVG, TLS). Code Review iniciada. | Tech Lead | Proof artifacts no /tmp | CODE REVIEW APROVADO |
| **CODE REVIEW APROVADO** | CR feedback incorporado, nenhuma objeção aberta. Pronto para merge. | Tech Lead | "Approved" label no GitHub | READY FOR COMMIT |
| **READY FOR COMMIT** | Todas as condições atendidas. Aguardando push. | Tech Lead | Merge ready signal | COMMIT |
| **COMMIT** | Efetivamente no repositório remoto (main/master). | DevOps/CI | Commit hash em main | MERGE |
| **MERGE** | Merge efetivada. Sprint item fechado. Release pode prosseguir. | DevOps | Release tag | (Próxima Sprint) |

### 7.3 Regras de Transição

1. **Sem pular estados**: Nunca IMPLEMENTADO → READY FOR COMMIT (pula VALIDADO)
2. **Forward only**: Exceto retorno explícito para ANÁLISE (motivo documentado)
3. **Transição deixa rastro**: Commit message, PR comment, ou SPRINT_vX_PLAN.md update
4. **Um estado por vez**: Não está em IMPLEMENTADO e VALIDADO simultaneamente
5. **Responsável pela transição**: Tech Lead assina cada transição (Git commit, GitHub label, ou comment)

---

## 8. Definition of Done

Checklist que DEVE ser verdade antes de qualquer merge.

### 8.1 Checklist DoD (Software Engineer + Tech Lead)

**ANTES de PR entrar em CODE REVIEW APROVADO:**

- [ ] **Código implementado**: Funcionalidade 100% per aceite criteria
- [ ] **Testes unitários**: ≥ 70% coverage no módulo alterado
- [ ] **Testes passando**: `pytest`, `npm test` — GREEN
- [ ] **Linting**: `ruff check .` e `npx eslint . --ext .ts,.tsx` — zero erros
- [ ] **Type checking**: `npx tsc --noEmit` — zero erros
- [ ] **Build**: `npm run build` — sem warnings, sem erros
- [ ] **Docker config**: `docker compose config` — válido
- [ ] **Documentação**: README/guides atualizados (se toca API)
- [ ] **Nenhum secret**: Verificar diff com regex de password/token/key
- [ ] **Nenhuma regressão arquitetural**: Principles 1-11 respeitadas
- [ ] **Commits claros**: Mensagens descrevem QUÊ e POR QUÊ
- [ ] **Git limpo**: Sem merge commits desnecessários
- [ ] **Rollback viável**: Plano de desfazer documentado ou trivial

**Qualquer caixa vazia = PR blocked até ser feita.**

### 8.2 Entrega Obrigatória

Junto com DoD checklist, SW Eng deve entregar:

```
1. Link para issue/task (no PR description)
2. Screenshots (se mudou UI)
3. Video/gif (se mudou comportamento complexo)
4. Test results (pytest/npm test output screenshot)
5. Rollback instructions (na description ou comments)
```

---

## 9. Processo Oficial de Code Review

3-Layer Validation + 4 Critical Gates. Nenhum "LGTM" cego.

### 9.1 As 3 Camadas de Validação

#### Camada 1: Syntax & Structure (ACG — Automated Code Generation Gate)

```
Valida:
✓ Sintaxe Python/TypeScript (sem erros de parse)
✓ Imports válidos (sem ImportError)
✓ Type hints (tsc --noEmit passa)
✓ Linting (ruff, eslint, passa)
✓ Build (npm run build sem erro)
```

**Quem certifica**: CI pipeline (GitHub Actions)  
**Tempo**: Automático (< 5 min)  
**Pass/Fail**: Automático

#### Camada 2: Logic & Integration (3LVG — Three-Layer Validation Gate)

```
Valida:
✓ Testes unitários passam (pytest, vitest)
✓ Integração passa (se houver)
✓ Coverage ≥ 70% no módulo
✓ Nenhum teste SKIPPED sem justificativa
✓ Nenhuma regressão em tests existentes
```

**Quem certifica**: CI pipeline + Tech Lead verifica report  
**Tempo**: 5-10 min  
**Pass/Fail**: Automático (fail se coverage < 70%)

#### Camada 3: Functional & Post-Deploy (TLS — Test-Level Staging Gate)

```
Valida:
✓ E2E tests passam (Playwright, se houver)
✓ Build de produção funciona (npm run build)
✓ Docker compose válido (docker compose config)
✓ Proof artifacts salvos (/tmp/proof-*.txt)
```

**Quem certifica**: Tech Lead (manual)  
**Tempo**: 15-30 min  
**Pass/Fail**: Manual approval

### 9.2 Os 4 Critical Gates (Antes de Approver)

Tech Lead DEVE executar estes 4 gates e documentar antes de clicar "Approve":

#### Gate 1: VPM — Verify Previous Modifications

```bash
# O que: Confirma que mudanças propostas realmente estão no código

# Comando:
git show HEAD:<arquivo> > /tmp/antes.txt
cat <arquivo> > /tmp/depois.txt
diff -u /tmp/antes.txt /tmp/depois.txt | tee /tmp/vpm-diff.txt

# Verificar: Tudo que foi proposto no PR aparece aqui?
```

**Fail se**: Mudanças propostas não aparecem no arquivo final

#### Gate 2: ACG — Automated Code Generation

```bash
# O que: Validar que código é sintaticamente válido

# Comandos:
ruff check . 2>&1 | tee /tmp/acg-ruff.txt
npx tsc --noEmit 2>&1 | tee /tmp/acg-tsc.txt
npx eslint . --ext .ts,.tsx 2>&1 | tee /tmp/acg-eslint.txt
pytest --collect-only 2>&1 | tee /tmp/acg-pytest-collect.txt

# Verificar: exit code 0 em todos
```

**Fail se**: Qualquer ferramenta retorna erro

#### Gate 3: 3LVG — Three-Layer Validation Gate

```bash
# O que: Validar que testes passam em todas as camadas

# Comandos:
pytest --cov=backend backend/tests/ -v 2>&1 | tee /tmp/3lvg-pytest.txt
npm test 2>&1 | tee /tmp/3lvg-npm-test.txt
npm run e2e 2>&1 | tee /tmp/3lvg-e2e.txt  # se houver

# Verificar:
# - exit code 0 em todos
# - coverage ≥ 70% (grep "TOTAL" do coverage report)
# - 0 SKIPPED tests (ou com @pytest.mark.skip("reason"))
```

**Fail se**: Qualquer teste falha ou coverage < 70%

#### Gate 4: TLS — Test-Level Staging

```bash
# O que: Validar que é safe para staging/produção

# Comandos:
npm run build 2>&1 | tee /tmp/tls-build.log
docker compose config > /dev/null 2>&1 && echo "Config valid" || (echo "Config invalid"; exit 1)

# Gerar proof artifacts:
git diff -- . > /tmp/tls-diff.txt
grep -n "Strict-Transport-Security\|Content-Security-Policy" docker/caddy/Caddyfile > /tmp/tls-headers.txt 2>&1 || true

# Se mudou API pública:
git diff -- backend/api/routes.py > /tmp/tls-api-diff.txt 2>&1 || true

# Verificar tudo em /tmp/tls-*.txt, /tmp/acg-*.txt, /tmp/3lvg-*.txt, /tmp/vpm-*.txt
```

**Fail se**: Build falha, docker inválido, ou proof artifacts ausentes

### 9.3 Checklist Code Review (Tech Lead)

**ANTES de clicar Approve:**

- [ ] PR description claro e linkado a issue
- [ ] Commits têm mensagens descritivas
- [ ] VPM Gate passou (mudanças estão no código)
- [ ] ACG Gate passou (syntax/type clean)
- [ ] 3LVG Gate passou (testes passam, coverage ✓)
- [ ] TLS Gate passou (build OK, proof artifacts ✓)
- [ ] Diff lido inteiro (não blind-approve)
- [ ] Nenhuma violação das Principles 1-11
- [ ] Documentação atualizada (se necessário)
- [ ] Nenhum secret em diff
- [ ] Rollback plan viável

**Se alguma caixa vazia ou vermelha: COMMENT (não approve) com motivo.**

---

## 10. Processo Oficial de Root Cause Analysis

Processo formal para investigar falhas críticas.

### 10.1 Quando Usar RCA

**Obrigatória para**:
- ❌ Código aprovado que não foi implementado
- ❌ Teste passou mas código não funciona
- ❌ Processo violado (commit sem PR, push sem CI)
- ❌ Security vulnerability passou despercebida
- ❌ Deployment causou downtime

**Recomendada para**:
- ⚠️ Resultado inesperado de processo correto
- ⚠️ Teste flaked ou skipped
- ⚠️ Violação de Principle por time member

### 10.2 10 Mandatory Sections

Toda RCA tem EXATAMENTE estas 10 seções, nesta ordem:

1. **Severity**: CRITICAL, HIGH, MEDIUM, LOW
2. **Timeline**: Quando descoberto, aprovado, detectado
3. **Failure Description**: O que foi esperado vs. real
4. **Root Cause**: POR QUÊ (técnico, sem blame)
5. **Principle Violations**: Quais principles foram violadas
6. **Process Gate Failures**: Quais gates falharam/não existiam
7. **Impact Assessment**: Quantas pessoas/sistemas afetados
8. **Corrective Actions**: Específicas, com donos, prazos
9. **Preventive Measures**: Como evitar recorrência
10. **Sign-off**: Data, assinatura de quem conduziu + aprovação

### 10.3 Severity Levels

| Nível | Definição | Resposta | Escalação |
|-------|-----------|----------|-----------|
| **CRITICAL** | Code aprovado que não existe; security bypass; data loss | < 1h | Chief Architect + Product Lead |
| **HIGH** | Processo violado; teste falhou; rollback necessário | 4h | Tech Lead + Product Lead |
| **MEDIUM** | Violação menor; gap de docs; teste flaky | 1 dia | Tech Lead |
| **LOW** | Cosmético; comentário antigo; docs desatualizada | 1 semana | Software Engineer |

### 10.4 Artefato

RCA é arquivo em:

```
docs/RCA/RCA_YYYYMMDD_<incident-name>.md
```

Exemplo: `docs/RCA/RCA_20260712_VULN1A_approval_fraud.md`

---

## 11. Processo de Release

Levar código de main/master para produção com validação em 3 camadas.

### 11.1 Pre-Release (24h antes)

**Checklist Tech Lead**:

- [ ] Release notes draft (o que mudou, por quê, impacto)
- [ ] Changelog atualizado (VERSION_HISTORY.md)
- [ ] Nenhum PR aberto contra main
- [ ] `git log main --oneline` mostra só commits desta Sprint
- [ ] Smoke test plan pronto (o que testar)
- [ ] Rollback plan escrito
- [ ] Stakeholders comunicados (Product, DevOps, QA)

### 11.2 Release Execution (DevOps)

1. **Tag**: `git tag -a v1.2.1 -m "Release v1.2.1 — [summary]"`
2. **Push**: `git push origin v1.2.1`
3. **CI runs**: GitHub Actions (build, testes, docker images)
4. **Deploy staging**: Manual approval, deploy containers
5. **Smoke tests**: Verificar de verdade em staging (login, flows)
6. **Deploy produção**: Manual approval de Chief Architect
7. **Verify**: Health checks, logs, metrics em produção
8. **Release notes**: GitHub Releases publicadas
9. **Communicate**: Slack/email ao time

### 11.3 Release Rollback

Se produção falha:

1. **Immediate**: Reverter docker image para anterior (sem code revert)
2. **Assess**: Hotfix (< 30min) ou rollback completo?
3. **Hotfix**: Bug fix, tag v1.2.1.1, re-deploy
4. **Full rollback**: Revert commits, re-tag, re-deploy
5. **Document**: RCA registrada (por quê falhou?)

---

## 12. Processo de Hotfix

Correções críticas fora da Sprint.

### 12.1 Critérios

Hotfix SÓ para:
- 🔴 Security vulnerabilities
- 🔴 Data loss risks
- 🔴 Critical path quebrado (login, dashboard)
- 🔴 Deployment failure (não inicia)

**NÃO para**:
- ❌ Novos features
- ❌ UI polish
- ❌ Logging
- ❌ Documentação
- ❌ Qualquer coisa que espera próxima Sprint

### 12.2 Workflow

```
1. Issue reportada (Slack alert, monitoring, usuário)
2. Tech Lead avalia: é realmente hotfix? (critérios acima)
3. Se SIM → autoriza; se NÃO → agenda próxima Sprint
4. Create branch: git checkout -b hotfix/v1.2.1.1_<name>
5. Fix + testes (mesmos gates de Sprint)
6. PR + code review (mesmos gatekeepers: TL)
7. Merge direto a main (sem esperar Sprint)
8. Tag v1.2.1.1, deploy imediato
9. RCA registrada (por que passou? como evitar?)
10. Postmortem no fim do dia (log em Slack)
```

---

## 13. Processo de Rollback

Reverter release em produção.

### 13.1 Tipos

| Tipo | Trigger | Tempo | Dados |
|------|---------|-------|-------|
| **Configuração** | Caddy/env problem | < 5 min | Nenhum |
| **Container** | Backend/frontend crash | < 10 min | Nenhum |
| **Database** | Migration destrutiva | 30 min - 2h | Possível perda |
| **Full Reversion** | Múltiplas camadas quebradas | 2-4h | Investigação |

### 13.2 Procedimento

**Config Rollback**:
```bash
git checkout HEAD~1 docker/caddy/Caddyfile
docker compose restart caddy
curl -I https://domain.com | grep 'expected-header'
```

**Container Rollback**:
```bash
# Encontrar última image boa
docker ps  # ou AWS ECR history
# Deploy imagem anterior
docker compose up -d backend:v1.2.0
# Verificar
curl -I https://api.domain.com/health
```

**Database Rollback**:
```bash
alembic current  # Qual versão?
alembic downgrade -1  # Voltar uma versão
# Verificar schema
```

### 13.3 Verification Checklist

Após rollback:

- [ ] `/health` endpoint retorna 200
- [ ] UI carrega (3+ browsers)
- [ ] Core workflows funcionam (login, enviar, buscar)
- [ ] Nenhum ERROR em logs
- [ ] Integridade de banco
- [ ] Dashboards green (response time, error rate)

**Se algum check falha: RCA necessária.**

---

## 14. Checklist do Software Engineer

Responsabilidades do início ao fim da Sprint.

### 14.1 Pre-Implementation

- [ ] Capability Gate aprovada
- [ ] Working Tree Gate aprovada
- [ ] Definition of Ready aprovada por Tech Lead
- [ ] Branch criada com nome claro (`feature/VULN-1A_hsts`)
- [ ] Nenhuma mudança em ARCHITECTURE_BASE.md

### 14.2 During Implementation

- [ ] Commits com mensagens descritivas (imperative tense)
- [ ] Nenhum `git push -f`
- [ ] Testes escritos ENQUANTO código é escrito
- [ ] Local tests passam: `pytest`, `npm test`, `npm run build`
- [ ] Nenhum TODO/FIXME sem issue linkada
- [ ] Ruff e ESLint passam: `ruff check .` e `npx eslint . --ext .ts,.tsx`
- [ ] Nenhum secret commitado

### 14.3 Before Opening PR

- [ ] Definition of Done checklist iniciado
- [ ] `git status` limpo
- [ ] Branch sincronizada: `git pull origin main` (resolve conflitos)
- [ ] PR description completo (não vago)
- [ ] Link para issue/task
- [ ] Screenshot/video (se mudou UI)
- [ ] Rollback plan na description

### 14.4 During Code Review

- [ ] Responde CR feedback dentro de 4 horas
- [ ] Faz changes rapidamente
- [ ] Não discute processo (só implementação)
- [ ] Commit novos (não amend) por feedback

### 14.5 After Approval

- [ ] Aguarda Tech Lead fazer merge
- [ ] Se CI falha pós-merge: hotfix imediato
- [ ] Documenta issues em postmortem

---

## 15. Checklist do Tech Lead

Responsabilidades operacionais durante toda Sprint.

### 15.1 Pre-Sprint Planning

- [ ] SPRINT_vX_PLAN.md escrito
- [ ] Bloqueadores identificados
- [ ] Risk register atualizado
- [ ] Team comunicado via Slack

### 15.2 During Implementation

- [ ] Responde bloqueadores em < 1 hora
- [ ] Daily standup: verifica progresso
- [ ] Documenta bloqueadores não-previstos
- [ ] Confia no processo (não micromanage)

### 15.3 Code Review & Gates (CRÍTICO)

- [ ] **VPM Gate**: Mudanças estão realmente no código
- [ ] **ACG Gate**: ruff, tsc, eslint passam
- [ ] **3LVG Gate**: pytest, npm test passam, coverage ≥ 70%
- [ ] **TLS Gate**: Build OK, docker válido, proof artifacts salvos
- [ ] Approve SÓ DEPOIS de todos 4 gates passarem
- [ ] Feedback é actionable (não "LGTM" vago)
- [ ] Aprova rapidamente se tudo está verde

### 15.4 Pre-Release

- [ ] Release notes revisadas
- [ ] Changelog atualizado
- [ ] Nenhum PR aberto
- [ ] Smoke test plan pronto
- [ ] Issues escaladas

### 15.5 Post-Release

- [ ] Monitora produção 1-2 horas
- [ ] Escalona hotfixes
- [ ] Conduz postmortem
- [ ] RCA escrita (se houve failure)
- [ ] Lessons learned documentadas

### 15.6 Process Governance

- [ ] Audita Principles 1-11 foram respeitados
- [ ] Se violation: RCA + propõe correção
- [ ] Atualiza ENGINEERING_PROCESS_v2.md se necessário
- [ ] Comunica mudanças ao time

---

## 16. Checklist do Chief Architect

Responsabilidades de integridade arquitetural.

### 16.1 Pre-Sprint

- [ ] Revisou SPRINT_vX_PLAN.md
- [ ] Se toca arquitetura: RFC aprovada ou "sem mudança" documentado
- [ ] Confirmou que Architecture Base v1.0 não será violada
- [ ] Aprovou blocos de código de complexidade alta

### 16.2 During Sprint

- [ ] Disponível para RFC/arquitetura questions (< 24h resposta)
- [ ] Faz code review em itens complexos (por delegação TL)
- [ ] Escalona issues arquiteturais

### 16.3 Pre-Release Approval

- [ ] Aprova release notes
- [ ] Assina off em deployment (autoriza produção)
- [ ] Autoriza rollback se necessário

### 16.4 Post-Release

- [ ] Revisou RCA (se houve failure)
- [ ] Propõe mudanças arquiteturais (agenda para próxima Sprint/RFC)
- [ ] Atualiza ARCHITECTURE_DECISIONS.md

### 16.5 Annual Tasks

- [ ] Revisita Architecture Base v1.0
- [ ] Propõe arquitetura v2.0 (se necessário)
- [ ] Treina novo Tech Lead

---

## 17. Evidências Obrigatórias

Nenhuma aprovação sem proof.

### 17.1 VPM Gate Proof

```
Arquivo: /tmp/vpm-diff.txt
Conteúdo: git diff output mostrando exatamente o que foi muda

Exemplo:
+ Strict-Transport-Security "max-age=31536000; includeSubDomains"
```

### 17.2 ACG Gate Proof

```
Arquivos: /tmp/acg-ruff.txt, /tmp/acg-tsc.txt, /tmp/acg-eslint.txt
Verificação: grep -c "error\|Error" /tmp/acg-*.txt → deve ser 0
```

### 17.3 3LVG Gate Proof

```
Arquivos: /tmp/3lvg-pytest.txt, /tmp/3lvg-npm-test.txt
Verificação: 
- grep "passed" ou "OK" em pytest/npm output
- grep "TOTAL" em coverage report → ≥ 70%
- grep -i "failed\|error" → deve ser 0
```

### 17.4 TLS Gate Proof

```
Arquivos: /tmp/tls-build.log, /tmp/tls-diff.txt, /tmp/tls-headers.txt
Verificação:
- grep "error\|failed" /tmp/tls-build.log → deve ser 0
- docker compose config exitcode → deve ser 0
```

### 17.5 Armazenamento

Todos os proof artifacts salvos em `/tmp/proof-*.txt` durante a sessão.  
Após sesão: Tech Lead copia para Issue/PR comment ou docs/evidence/ para audit.

---

## 18. Situações que Bloqueiam uma Sprint

Nenhuma Sprint começar se qualquer uma destas for verdade.

### 18.1 Bloqueadores de Infraestrutura

- [ ] ❌ Capability Gate falha (Python/Node não disponível)
- [ ] ❌ Working Tree não está limpa (uncommitted changes ou stash antigo)
- [ ] ❌ CI pipeline fora (GitHub Actions inacessível)
- [ ] ❌ Repository não clonado ou não sincronizado

**Remediação**: Tech Lead escalona para Chief Architect. Sem infraestrutura = sem Sprint.

### 18.2 Bloqueadores de Processo

- [ ] ❌ Definition of Ready não foi feito (nenhum item tem DoR checklist)
- [ ] ❌ Definition of Done não foi acordado (team não sabe o que "pronto" significa)
- [ ] ❌ SPRINT_vX_PLAN.md não existe ou está vago
- [ ] ❌ Rollback plan não documentado para nenhum item

**Remediação**: Tech Lead + Product Lead completam documentação. Sprint não começa até estar pronta.

### 18.3 Bloqueadores de RFC

- [ ] ❌ Item toca arquitetura, RFC não foi aprovada por Chief Architect
- [ ] ❌ Item viola uma das Principles 1-11, sem RFC explícita aprovando exceção

**Remediação**: RFC criada, revisada, aprovada. Pode levar 24-48h.

### 18.4 Bloqueadores de Dependência

- [ ] ❌ Item A depende de item B, mas B não está READY FOR COMMIT

**Remediação**: Reorder Sprint para B ir primeiro, ou aiar item A para próxima Sprint.

### 18.5 Bloqueadores de Segurança

- [ ] ❌ Security review não foi feito (se item toca auth, crypto, API)
- [ ] ❌ Secrets encontrados em código anterior não foram removidos

**Remediação**: Security specialist faz review, ou item adiado.

### 18.6 Bloqueadores de Risk

- [ ] ❌ High-risk item sem Rollback plan testado
- [ ] ❌ Change affecting data without expand-contract migration strategy

**Remediação**: Rollback plan escrito + testado, ou migration strategy aprovada.

---

## 19. Fluxograma Completo do Ciclo de Vida de uma Tarefa

```
┌────────────────────────────────────────────────────────┐
│ SPRINT PLANNING                                        │
│ Product Lead + Tech Lead                               │
│ ✓ Backlog → SPRINT_vX_PLAN.md                         │
│ ✓ Bloqueadores documentados                           │
│ ✓ Rollback plans esboçados                            │
│ → Aprovação do Tech Lead                             │
└────────────────────────────────────────────────────────┘
              ↓
┌────────────────────────────────────────────────────────┐
│ TASK: ANÁLISE                                          │
│ Item no backlog, sem comprometimento                  │
└────────────────────────────────────────────────────────┘
              ↓
    ┌────────────────────────────────┐
    │ Definition of Ready aprovada?  │
    ├────────────────┬───────────────┤
    │ NÃO            │ SIM           │
    ↓                ↓               ↓
 ┌──────┐    ┌──────────────────────────────┐
 │VOLTA │    │ TASK: APROVADO PARA          │
 │ANÁLISE    │ IMPLEMENTAÇÃO                │
 │+ RCA │    │                              │
 │(retry)   │ Tech Lead: ✓ DoR completo   │
 └──────┘    │ SW Eng pode começar         │
             └──────────────────────────────┘
                      ↓
         ┌────────────────────────────┐
         │ TASK: IMPLEMENTADO         │
         │                            │
         │ SW Eng:                   │
         │ ✓ Código escrito          │
         │ ✓ Testes adicionados      │
         │ ✓ Tests passam localmente │
         │ ✓ PR aberto              │
         └────────────────────────────┘
                      ↓
         ┌────────────────────────────┐
         │ TASK: VALIDADO             │
         │                            │
         │ Tech Lead executa:         │
         │ ✓ VPM Gate                │
         │ ✓ ACG Gate                │
         │ ✓ 3LVG Gate               │
         │ ✓ TLS Gate                │
         │ ✓ Proof artifacts salvos   │
         └────────────────────────────┘
                      ↓
    ┌────────────────────────────────┐
    │ Todos 4 Gates passaram?       │
    ├────────────┬──────────────────┤
    │ NÃO        │ SIM              │
    ↓            ↓                  ↓
 ┌────────┐   ┌───────────────────────────────┐
 │COMMENT │   │ TASK: CODE REVIEW APROVADO    │
 │on PR   │   │                               │
 │request │   │ Tech Lead:                   │
 │changes │   │ ✓ Diff revisado              │
 │        │   │ ✓ Nenhum secret              │
 │← loop  │   │ ✓ Principles OK              │
 │IMPLEMENT   │ ✓ Click APPROVE no GitHub    │
 └────────┘   └───────────────────────────────┘
                      ↓
         ┌────────────────────────────┐
         │ TASK: READY FOR COMMIT     │
         │                            │
         │ Tech Lead:                │
         │ ✓ CI green               │
         │ ✓ DoD checklist completo │
         └────────────────────────────┘
                      ↓
         ┌────────────────────────────┐
         │ TASK: COMMIT               │
         │                            │
         │ DevOps/CI:                │
         │ ✓ Push a main            │
         │ ✓ CI pipeline runs       │
         │ ✓ Tests passam           │
         └────────────────────────────┘
                      ↓
         ┌────────────────────────────┐
         │ TASK: MERGE                │
         │                            │
         │ ✓ Merge completa          │
         │ ✓ Ready para release      │
         └────────────────────────────┘
                      ↓
┌────────────────────────────────────────────────────────┐
│ RELEASE (Seção 11)                                    │
│ • Tag release                                        │
│ • Deploy staging                                     │
│ • Smoke tests                                        │
│ • Deploy produção                                    │
│ • Post-deploy verification                          │
│                                                      │
│ IF FAILURE → Seção 13 (Rollback) + RCA             │
│ IF SUCCESS → Postmortem                            │
└────────────────────────────────────────────────────────┘
```

---

## 20. Lições Aprendidas da Falha VULN-1A

Incident ocorrido em 2026-07-12. Code Review aprovou implementação que não existia.

### 20.1 Timeline da Falha

```
14:30 → Edit tool chamada (objetivo: adicionar HSTS header)
15:00 → Code Review aprovada (sem verificação de VPM Gate)
15:30 → Deploy para staging autorizado
16:45 → Verificação manual: grep -n "Strict-Transport-Security" → VAZIO
16:50 → git diff: NENHUMA MUDANÇA
17:00 → RCA iniciada (Severity: CRITICAL)
```

### 20.2 Root Cause (Técnico, sem Blame)

**Primary**: Não havia verificação de Read-back após Edit tool.  
**Secondary**: Proof artifacts não eram obrigatórios em Code Review.  
**Tertiary**: VPM Gate não existia como gate formal.

### 20.3 Principle Violations

- ❌ **Principle 7** (Validate code first): Código não foi validado de fato
- ❌ **Principle 9** (Artifacts > Assumption): CR não pediu proof artifacts
- ❌ **Principle 11** (Tech Lead Gatekeeping): CR foi feita sem gates formais

### 20.4 Process Gate Failures

| Gate | Status | Razão |
|------|--------|-------|
| VPM | Não existia | Nenhuma verificação de "mudança foi feita" |
| ACG | Não aplicável | Mudança era em Caddyfile (não código) |
| 3LVG | Não aplicável | Mudança era em config, não lógica |
| TLS | Não executada | Tech Lead não rodou verification commands |

### 20.5 Corrective Actions Implementadas

| Ação | Dono | Prazo | Status |
|------|------|-------|--------|
| Adicionar VPM Gate como mandatory | Tech Lead | 24h | ✓ Implementado |
| Adicionar ACG Gate como mandatory | Tech Lead | 24h | ✓ Implementado |
| Adicionar 3LVG Gate como mandatory | Tech Lead | 24h | ✓ Implementado |
| Adicionar TLS Gate como mandatory | Tech Lead | 24h | ✓ Implementado |
| Documentar proof artifacts obrigatórias | Tech Lead | 24h | ✓ Seção 17 |
| Criar ENGINEERING_PROCESS_v2.md | Tech Lead | 48h | ✓ Este documento |

### 20.6 Preventive Measures

1. **Proof Artifacts Obrigatórias** (Seção 17)
   - Nenhuma Code Review sem /tmp/proof-*.txt
   - Artifacts linkadas no PR comment

2. **4 Gates Formais Agora**
   - VPM: git diff validação
   - ACG: syntax/type checking
   - 3LVG: test/coverage validation
   - TLS: build/docker/staging validation

3. **Read-Back Verification** (nova prática)
   - Após Edit tool: sempre Read arquivo novamente
   - Verifica que mudança foi persistida

4. **Tech Lead Checklist** (Seção 15)
   - Agora tem "✓ Todos 4 Gates ejecutados"
   - Não é mais discricional

### 20.7 Lessons

- **Lesson 1**: Approval sem validação = ilusão de rigor. Gates precisam de execução, não só teoria.
- **Lesson 2**: Proof artifacts salvam vidas. "git diff" é o mínimo; precisa de mais.
- **Lesson 3**: Tech Lead não é reviewador; é gatekeeper. Diferença crítica.
- **Lesson 4**: Processo > Confiança. Confiança sem processo = VULN-1A.

### 20.8 Caso de Uso: "Isso nunca mais vai acontecer"

Cenário: Mesmo edit tool call, mesma mudança proposta.

**Antes (BROKEN)**:
```
1. SW Eng usa Edit tool
2. Tech Lead faz CR (sem verificação)
3. Approve (confiança em tool)
4. Deploy (falha em produção)
```

**Agora (FIXED)**:
```
1. SW Eng usa Edit tool
2. Tech Lead valida VPM Gate:
   git show HEAD:file.txt > /tmp/antes.txt
   cat file.txt > /tmp/depois.txt
   diff -u /tmp/antes.txt /tmp/depois.txt
3. Se diff mostra mudança: prossegue
4. Se diff vazio: REJECT ("mudança não foi persistida")
5. SW Eng re-tenta (ou report tool bug)
6. Só depois que VPM passa: aciona ACG, 3LVG, TLS
7. Deploy com confidence
```

---

## Resumo Executivo

Este documento consolida **11 Princípios Obrigatórios**, **4 Gates Críticos**, **8-State Machine**, 
**5 Processos Completos**, e **3 Checklists Executáveis**.

**O que mudou pós-VULN-1A**:
- ✅ VPM Gate (Verify Previous Modifications)
- ✅ Proof artifacts obrigatórias em Code Review
- ✅ Tech Lead Gatekeeping formalizado
- ✅ RCA 10-section process criada
- ✅ ENGINEERING_PROCESS_v2.md é single source of truth

**Validação de processo**:
- Antes: Assumiu-se confiança (FAILED)
- Agora: Assume-se execução de gates (PROVEN)

**Próximas ações**:
1. Chief Architect aprova documento (assinatura/email)
2. Tech Lead distribui ao team
3. Primeira Sprint com ENGINEERING_PROCESS_v2.md começa
4. Postmortem de cada Sprint audita compliance

---

**FIM DO DOCUMENTO**

Documento é single source of truth de engenharia da Plataforma Dario.  
Toda mudança futura requer RFC e aprovação do Tech Lead + Chief Architect.  
Nenhuma Sprint pode começar sem compliance total a este processo.
