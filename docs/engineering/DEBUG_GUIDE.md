# Debug Guide

## 1. Reproduzir Bugs

### Template de Bug Report
```markdown
**Severidade:** P0 | P1 | P2 | P3

**Descrição:** O que acontece vs. o que deveria acontecer

**Passos para Reproduzir:**
1. ...
2. ...
3. ...

**Dados de Entrada:**
- Mensagem: "..."
- Contact ID: ...
- Timestamp: ...

**Comportamento Esperado:** ...

**Comportamento Real:** ...

**Logs Relevantes:** (anexar ou colar trecho)

**Ambiente:**
- Versão: v1.x.x
- Provider: openai | gemini | ...
- Database: postgres | sqlite
```

### Checklist de Reprodução
- [ ] Reproduzir pelo menos 3 vezes
- [ ] Testar em ambiente limpo (sem cache)
- [ ] Isolar variáveis (um fator por vez)
- [ ] Documentar condições exatas (hora, provider, dados)

---

## 2. Coleta de Logs

### Níveis de Log
| Nível | Quando Usar | Exemplo |
|-------|-------------|---------|
| **DEBUG** | Detalhamento interno | "Intent classified as GREETING (0.95)" |
| **INFO** | Fluxo normal | "Job started: whatsapp.send_message" |
| **WARNING** | Recuperação automática | "LLM timeout, retrying with fallback" |
| **ERROR** | Falha recuperável | "Tool execution failed: invalid arguments" |
| **CRITICAL** | Falha sistêmica | "Database connection lost" |

### Ativar Debug
```bash
# Backend
export LOG_LEVEL=DEBUG
python -m uvicorn backend.main:app --log-level debug

# Frontend
export NEXT_PUBLIC_LOG_LEVEL=debug
npm run dev
```

### Extrair Logs por Request ID
```bash
# Todos logs de uma requisição específica
grep "request_id=abc123" logs/app.log

# Filtrar por nível
grep "ERROR" logs/app.log | grep "2024-01-15"

# Formatado com jq (logs JSON)
cat logs/app.log | jq 'select(.request_id == "abc123")'
```

### Localização de Logs
| Ambiente | Caminho |
|----------|---------|
| **Dev (local)** | `logs/app.log` |
| **Docker** | `docker-compose logs -f api` |
| **Produção** | `/var/log/dario-os/app.log` |
| **Systemd** | `journalctl -u dario-os -f` |

---

## 3. Debugging Interativo

### Python (pdb)
```python
# Inserir breakpoint
import pdb; pdb.set_trace()

# Ou Python 3.7+
breakpoint()

# Comandos úteis:
# n (next) - próxima linha
# s (step) - entrar na função
# c (continue) - continuar execução
# p <var> - imprimir variável
# l (list) - mostrar código ao redor
```

### VS Code Debugger
```json
// .vscode/launch.json
{
    "name": "Dario OS: Backend",
    "type": "python",
    "request": "launch",
    "module": "uvicorn",
    "args": ["backend.main:app", "--reload"],
    "cwd": "${workspaceFolder}",
    "env": {"LOG_LEVEL": "DEBUG"}
}
```

### Logging Estratégico
```python
import logging

logger = logging.getLogger(__name__)

async def process_message(message: str, contact_id: int):
    logger.debug(f"Processing message from contact {contact_id}")
    
    try:
        result = await classify_intent(message)
        logger.info(f"Intent classified: {result.intent}")
        return result
    except Exception as e:
        logger.error(f"Classification failed: {e}", exc_info=True)
        raise
```

---

## 4. Incidentes

### Classificação de Severidade
| Nível | Impacto | Tempo de Resposta | Exemplo |
|-------|---------|-------------------|---------|
| **P0** | Sistema fora do ar | Imediato (< 15min) | API não responde, DB down |
| **P1** | Funcionalidade crítica quebrada | < 1h | WhatsApp não envia mensagens |
| **P2** | Funcionalidade não-crítica | < 4h | Dashboard lento, métricas falhando |
| **P3** | Bug cosmético ou raro | < 24h | UI desalinhada, erro ocasional |

### Processo de Abertura

#### P0/P1 (Crítico)
1. **Imediato:** Notificar canal `#incidentes` + on-call
2. **Ação:** Iniciar troubleshooting e mitigação
3. **Atualização:** Status a cada 30min até resolução
4. **Post-Mortem:** Obrigatório em até 24h

#### P2/P3 (Não-Crítico)
1. Abrir issue no GitHub/GitLab
2. Priorizar no backlog da sprint
3. Resolver dentro do SLA

### Template de Post-Mortem
```markdown
# Post-Mortem: [Título do Incidente]

**Data:** YYYY-MM-DD HH:MM  
**Severidade:** P0 | P1  
**Duração:** X horas Y minutos  
**Impacto:** [Descrição do impacto nos usuários]

## Linha do Tempo
- HH:MM - Incidente iniciado
- HH:MM - Detectado por [monitoring/usuário]
- HH:MM - Equipe notificada
- HH:MM - Mitigação aplicada
- HH:MM - Serviço restaurado

## Causa Raiz
[Explicação técnica detalhada]

## Ações Corretivas
- [ ] Ação 1 (responsável, prazo)
- [ ] Ação 2 (responsável, prazo)

## Lições Aprendidas
- O que funcionou bem
- O que pode melhorar
- Como prevenir recorrência
```

---

## 5. Evidências

### O Que Coletar
| Tipo | Quando | Como |
|------|--------|------|
| **Logs** | Sempre | `tail -f logs/app.log > incident.log` |
| **Screenshots** | Bugs de UI | Print + anotações |
| **HAR File** | Problemas de rede | DevTools → Network → Export HAR |
| **Request/Response** | APIs | `curl -v` ou Postman export |
| **DB State** | Dados corrompidos | `pg_dump` ou query específica |
| **Metrics** | Performance | Screenshot Grafana/Prometheus |

### Sanitização de Dados
**Nunca compartilhar:**
- Tokens de API
- Senhas ou credenciais
- Dados pessoais de usuários (LGPD)
- Chaves privadas

**Sempre ofuscar:**
```bash
# Substituir tokens
sed -i 's/sk-[a-zA-Z0-9]\{32,\}/sk-***REDACTED***/g' logs.txt

# Substituir emails
sed -i 's/[a-z0-9._%+-]\+@[a-z0-9.-]\+\.[a-z]\{2,\}/***@redacted/g' logs.txt
```

---

## 6. Regressões

### Identificar Commit Causador
```bash
# Git bisect (busca binária)
git bisect start
git bisect bad          # Versão atual (com bug)
git bisect good v1.2.0  # Versão anterior (sem bug)

# Git testa commits intermediários
# Para cada um: testar e marcar
git bisect good  # ou git bisect bad

# Ao final: git mostra commit causador
git bisect reset  # Limpar bisect
```

### Template de Documentação de Regressão
```markdown
# Regressão: [Nome do Bug]

**Detectado em:** v1.x.x  
**Última versão OK:** v1.y.y  
**Commit causador:** `abc123def` (link)

**Funcionalidade Afetada:** ...

**Causa:** 
- [ ] Mudança de lógica
- [ ] Refatoração incompleta
- [ ] Teste faltante
- [ ] Dependência atualizada
- [ ] Outro: ...

**Teste Faltante:** 
[Descrever qual teste teria pegado isso]

**Ação Preventiva:**
- [ ] Adicionar teste E2E para cenário X
- [ ] Melhorar cobertura no módulo Y
- [ ] Atualizar definição de done
```

---

## 7. Debug Checklist

### Antes de Reportar
- [ ] Reproduziu o bug 3 vezes?
- [ ] Testou em ambiente limpo?
- [ ] Coletou logs completos?
- [ ] Isolou o mínimo necessário para reproduzir?
- [ ] Verificou se não é problema de configuração?

### Durante Investigação
- [ ] Ativou log level DEBUG?
- [ ] Verificou métricas (latência, erro, throughput)?
- [ ] Testou com dados diferentes?
- [ ] Verificou dependências externas (LLM, WhatsApp)?
- [ ] Olhou histórico de mudanças recentes?

### Após Resolução
- [ ] Documentou causa raiz?
- [ ] Adicionou teste para prevenir recorrência?
- [ ] Atualizou documentação se necessário?
- [ ] Compartilhou aprendizado com equipe?

---

## 8. Ferramentas

| Ferramenta | Uso | Comando |
|------------|-----|---------|
| **pytest** | Rodar testes | `pytest -v --tb=short` |
| **coverage** | Ver cobertura | `coverage html && open htmlcov/index.html` |
| **jq** | Parse JSON logs | `cat log.jsonl \| jq .` |
| **htop** | Monitorar recursos | `htop` |
| **tcpdump** | Capturar tráfego | `tcpdump -i any -w capture.pcap` |
| **curl** | Testar APIs | `curl -v http://localhost:8000/api/health` |
| **pgcli** | Debug DB | `pgcli postgresql://...` |

---

## KPIs de Debug

| Métrica | Meta | Como Medir |
|---------|------|------------|
| **MTTR (P0)** | < 2h | Tempo detecção → resolução |
| **MTTR (P1)** | < 4h | Tempo detecção → resolução |
| **Bugs reabertos** | < 5% | Issues reabertas / total |
| **Regressões** | 0/mês | Bugs em features existentes |
| **Tempo reprodução** | < 30min | Tempo para isolar bug |
