# Definition of Done (DoD)

## Checklist Obrigatório

Uma tarefa só é considerada **CONCLUÍDA** quando todos os itens abaixo estão marcados:

### 1. Código
- [ ] Implementado conforme requisitos
- [ ] Formatado (black/ruff para Python, prettier para TS)
- [ ] Lint limpo (zero warnings/errors)
- [ ] Segue padrões do projeto (naming, estrutura)

### 2. Tipagem
- [ ] Type hints completos (Python) ou tipos (TypeScript)
- [ ] Zero erros de mypy/tsc
- [ ] Sem `any` ou `type: ignore` sem justificativa

### 3. Testes
- [ ] Testes unitários criados para nova lógica
- [ ] Testes de integração para limites de módulos
- [ ] E2E para fluxos críticos (se aplicável)
- [ ] Todos testes passando
- [ ] Cobertura ≥ 85% (backend) ou ≥ 75% (frontend)
- [ ] Cobertura total do projeto não diminuiu

### 4. Segurança
- [ ] Sem segredos hard-coded (tokens, senhas)
- [ ] Inputs validados contra schema
- [ ] Outputs sanitizados (logs, respostas)
- [ ] Autenticação/autorização verificadas

### 5. Documentação
- [ ] Docstrings em funções/métodos públicos
- [ ] README atualizado (se API mudou)
- [ ] Variáveis de ambiente documentadas em `.env.example`
- [ ] Changelog atualizado (se feature ou bug fix relevante)

### 6. Observabilidade
- [ ] Logs estruturados em pontos críticos
- [ ] Níveis de log apropriados (DEBUG, INFO, ERROR)
- [ ] Métricas expostas (se aplicável: latência, contadores)
- [ ] Request ID propagado

### 7. Performance
- [ ] Sem N+1 queries
- [ ] Loops otimizados (evitar O(n²) desnecessário)
- [ ] Timeouts configurados em chamadas externas
- [ ] Cache aplicado onde apropriado

### 8. Compatibilidade
- [ ] Não quebra APIs existentes (sem breaking changes)
- [ ] Migração de DB criada e testada (se schema mudou)
- [ ] Rollback testado (se mudança crítica)

### 9. Review
- [ ] Self-review realizado
- [ ] Code review aprovado (1 aprovador mínimo)
- [ ] Comentários do review endereçados
- [ ] CI/CD passando (todos gates verdes)

### 10. Deploy
- [ ] Validado em staging (se disponível)
- [ ] Plano de rollback definido (se crítico)
- [ ] Monitoramento configurado (alertas, dashboards)

---

## Critérios de Rejeição Automática

| Cenário | Ação |
|---------|------|
| Testes falhando | ❌ Rejeitar |
| Cobertura diminuiu | ❌ Rejeitar |
| Lint/typecheck com erro | ❌ Rejeitar |
| Segredo hard-coded detectado | ❌ Rejeitar |
| Breaking change sem aviso | ❌ Rejeitar |
| Migration sem rollback | ❌ Rejeitar |
| Security scan com vulnerabilidade alta | ❌ Rejeitar |

---

## Níveis de Done

| Nível | Descrição | Quando Aplicar |
|-------|-----------|----------------|
| **Done Mínimo** | Checklist 1-4 completo | Bug fixes simples |
| **Done Ideal** | Checklist 1-10 completo | Features novas, refatorações |
| **Done Técnico** | Código + testes + lint | PR merged, não deployado |
| **Done Negócio** | Em produção + monitorado | Feature liberada ao usuário |

---

## Validação por Tipo de Tarefa

| Tipo | Testes Unitários | Integração | E2E | Docs | Rollback |
|------|------------------|------------|-----|------|----------|
| **Bug Fix** | ✅ Obrigatório | ⚠️ Se afeta limite | ❌ Raro | ⚠️ Se mudar comportamento | ⚠️ Se crítico |
| **Feature Nova** | ✅ Obrigatório | ✅ Obrigatório | ✅ Críticos | ✅ Obrigatório | ✅ Se crítico |
| **Refatoração** | ✅ Manter cobertura | ⚠️ Se mudar interface | ❌ Raro | ❌ Interno | ⚠️ Se arriscada |
| **Hotfix** | ⚠️ Mínimo viável | ❌ Urgência | ❌ Urgência | ❌ Pós-fix | ✅ Definir |
| **Chore** | ❌ N/A | ❌ N/A | ❌ N/A | ⚠️ Se relevante | ❌ N/A |

---

## Template de Submissão para Review

```markdown
## Tarefa: [Nome da Tarefa]

### Checklist DoD
- [ ] Código implementado e formatado
- [ ] Tipagem completa (zero erros mypy/tsc)
- [ ] Testes criados e passando
- [ ] Cobertura ≥ 85% (backend) / 75% (frontend)
- [ ] Segurança verificada (sem segredos, inputs validados)
- [ ] Documentação atualizada
- [ ] Logs estruturados adicionados
- [ ] Performance verificada (sem N+1, timeouts)
- [ ] Compatibilidade mantida (sem breaking changes)
- [ ] Review aprovado

### Tipo de Mudança
- [ ] Bug fix
- [ ] Feature nova
- [ ] Refatoração
- [ ] Hotfix
- [ ] Outro: _____

### Testing Done
- Testes unitários: X adicionados, Y totais
- Testes de integração: X adicionados
- E2E: X cenários cobertos
- Cobertura: Z% (antes: W%)

### Riscos Conhecidos
- [Nenhum / Descrever se houver]

### Rollback Plan
- [Simples revert / Requer migration reversa / Outro]

### Screenshots/Evidências
[Se aplicável]
```

---

## Processo de Validação

```
┌─────────────┐
│ Self-Review │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Code Review │ (1+ aprovador)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   CI/CD     │ (Todos gates verdes)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Aprovação │ (Merge)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Pós-Deploy  │ (Monitoramento)
└─────────────┘
```

---

## KPIs de Conformidade

| Métrica | Meta | Como Medir |
|---------|------|------------|
| **Tarefas com DoD completo** | 100% | Audit amostral de PRs |
| **Bugs por falta de teste** | 0 | Post-mortem analysis |
| **Rollbacks não planejados** | 0 | Deploy logs |
| **Regressões em produção** | < 1/mês | Issue tracking |
| **Tempo médio de review** | < 24h | GitHub/GitLab metrics |

---

## Guia de Decisão Rápida

| Pergunta | Resposta | Ação |
|----------|----------|------|
| Precisa de teste? | Tem lógica nova? | ✅ Sim |
| Precisa de doc? | API mudou? | ✅ Sim |
| É breaking change? | Altera contrato? | ⚠️ Avisar no changelog |
| Precisa de migration? | Schema do DB mudou? | ✅ Criar + testar |
| Precisa de rollback? | É crítico? | ✅ Definir plano |

---

## Escalonamento de Disputas

Se houver discordância sobre "está done":

1. **Nível 1:** Discutir entre autor e reviewer
2. **Nível 2:** Envolver tech lead
3. **Nível 3:** Consultar arquiteto (se técnico)
4. **Nível 4:** Decisão do PO (se negócio)

**Regra de Ouro:** *Em caso de dúvida, inclinar-se para qualidade. Melhor atrasar um dia do que entregar com dívida técnica.*
