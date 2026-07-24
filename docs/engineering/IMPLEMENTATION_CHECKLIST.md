# Implementation Checklist

## 1. Fluxo de Implementação

### Fase 1: Preparação (Obrigatório)
- [ ] Ler `MASTER_CONTEXT.md`, `CURRENT_SPRINT.md` e `AGENT_RULES.md`
- [ ] Identificar arquivos afetados e dependências
- [ ] Definir estratégia de teste antes de codificar
- [ ] Criar branch feature (`feature/<nome-tarefa>`)

### Fase 2: Codificação
- [ ] Seguir padrões existentes (naming, estrutura, estilo)
- [ ] Manter funções pequenas (< 50 linhas) e com única responsabilidade
- [ ] Adicionar type hints completos (Python) ou tipos (TypeScript)
- [ ] Incluir logs estruturados em pontos críticos
- [ ] Não alterar arquitetura sem aprovação explícita

### Fase 3: Validação Local
```bash
# Backend
ruff check . && ruff format .
mypy backend/
pytest backend/tests/ -v --cov=backend --cov-fail-under=85

# Frontend
npm run lint && npm run format
npm run typecheck
npm test -- --coverage --threshold=75
```

---

## 2. Fluxo de Revisão (Code Review)

### Critérios Obrigatórios
| Critério | Verificação |
|----------|-------------|
| **Funcionalidade** | Atende aos requisitos da tarefa? |
| **Testes** | Cobertura ≥ 85% (backend), ≥ 75% (frontend)? |
| **Tipagem** | Zero erros de mypy/tsc? |
| **Lint** | Zero warnings de ruff/eslint? |
| **Segurança** | Sem segredos hard-coded? Inputs validados? |
| **Performance** | Sem N+1 queries? Loops otimizados? |
| **Legibilidade** | Código autoexplicativo? Comentários apenas no "porquê"? |

### Aprovações Necessárias
- **Bug fix simples:** 1 aprovador
- **Nova feature:** 1 aprovador sênior
- **Mudança arquitetural:** Arquiteto + 1 sênior
- **Hotfix produção:** 1 aprovador (revisão post-merge obrigatória)

---

## 3. Fluxo de Testes

### Pirâmide de Testes
```
        /\
       /  \      E2E (10%) - Críticos apenas
      /----\    
     /      \   Integration (20%) - Limites de módulos
    /--------\  
   /          \ Unit (70%) - Lógica de negócio
  /------------\ 
```

### Quando Criar Cada Tipo
| Tipo | Quando Criar | Exemplo |
|------|--------------|---------|
| **Unit** | Toda nova função/método com lógica | `test_classify_intent()` |
| **Integration** | Interação com DB, API externa, fila | `test_job_queue_persistence()` |
| **E2E** | Fluxo crítico de usuário | `test_whatsapp_message_flow()` |

### Regras de Teste
- Nome descritivo: `test_<acao>_quando_<condicao>_deve_<resultado>`
- Isolado: Não depende de ordem de execução
- Determinístico: Mesmo input → mesmo output sempre
- Rápido: Unit < 100ms, Integration < 1s, E2E < 10s

---

## 4. Fluxo de Validação

### Checklist Pré-Merge
- [ ] Todos testes passando localmente
- [ ] Cobertura não diminuiu
- [ ] Lint e typecheck limpos
- [ ] Documentação atualizada (se API mudou)
- [ ] Logs adicionados em pontos críticos
- [ ] Variáveis de ambiente documentadas (`.env.example`)
- [ ] Migration criada e testada (se schema mudou)
- [ ] Rollback testado (se mudança crítica)

### Validação Automática (CI)
```yaml
stages:
  - lint          # ruff, eslint
  - typecheck     # mypy, tsc
  - test-unit     # pytest, jest
  - test-integration
  - build         # docker build, npm build
  - security-scan # bandit, npm audit
```

---

## 5. Fluxo de Rollback

### Níveis de Rollback

#### Nível 1: Reverter Commit (Mais comum)
```bash
git revert <commit-hash>
git push origin main
```
**Quando:** Bug descoberto antes do deploy ou em staging.

#### Nível 2: Redeploy Versão Anterior
```bash
# Docker
docker-compose down
git checkout <tag-anterior>
docker-compose up -d
```
**Quando:** Bug em produção sem migrações incompatíveis.

#### Nível 3: Rollback com Migração Reversa
```bash
# Alembic (exemplo)
alembic downgrade -1
git checkout <tag-anterior>
docker-compose up -d
```
**Quando:** Migração de banco causou problema.

### Procedimento de Emergência (P0)
1. **Imediato:** Reverter deploy (Nível 2 ou 3)
2. **Comunicação:** Notificar canal `#incidentes` com:
   - O que falhou
   - Impacto estimado
   - Ação tomada
3. **Post-Mortem:** Abrir issue com análise de causa raiz em até 24h
4. **Fix:** Criar hotfix branch, testar, deploy separado do rollback

---

## Gatekeepers (Impedem Avanço)

| Gate | Critério | Bloqueia Se |
|------|----------|-------------|
| **G1** | Testes unitários | Qualquer falha |
| **G2** | Cobertura | Diminuição > 0.5% |
| **G3** | Typecheck | Qualquer erro |
| **G4** | Lint | Qualquer erro |
| **G5** | Security scan | Vulnerabilidade alta/crítica |
| **G6** | Integration tests | Qualquer falha |
| **G7** | Build | Falha no build Docker/Next.js |

**Regra:** Nenhum merge sem passar por todos os gates.
