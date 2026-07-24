# Testing Standard

## 1. Pirâmide de Testes

```
        /\
       /  \      E2E (10%) - Fluxos críticos
      /----\    
     /      \   Integration (20%) - Limites de módulos
    /--------\  
   /          \ Unit (70%) - Lógica de negócio
  /------------\ 
```

**Tempos Máximos:**
- Unit: < 100ms cada
- Integration: < 1s cada
- E2E: < 10s cada

---

## 2. Unit Tests

### Quando Criar
- Toda função/método com lógica de negócio
- Classes com múltiplos caminhos de execução
- Handlers de tools, agents, orchestrator

### Estrutura (AAA Pattern)
```python
def test_classify_intent_when_greeting_should_return_personal_agent():
    # Arrange
    message = "Olá, bom dia!"
    
    # Act
    result = intent_classifier.classify(message)
    
    # Assert
    assert result.intent == Intent.GREETING
    assert result.confidence > 0.9
```

### Regras
- Nome: `test_<acao>_quando_<condicao>_deve_<resultado>`
- Isolado: Sem dependência entre testes
- Determinístico: Mesmo input → mesmo output
- Rápido: < 100ms

### O Que Mockar
| Mockar | Não Mockar |
|--------|------------|
| APIs externas (LLM, WhatsApp) | Lógica interna da classe testada |
| Banco de dados | Funções utilitárias puras |
| File system | Validações de schema |
| Tempo (`freezegun`) | Cálculos matemáticos |

---

## 3. Integration Tests

### Quando Criar
- Interação com banco de dados
- Chamadas a serviços externos (via mock)
- Event Bus pub/sub
- Job queue persistence

### Estratégia de DB
```python
# Usar transação rollbackada
async def test_job_repository_persistence(db_session):
    repo = JobRepository(db_session)
    job = await repo.create(JobCreate(type="test"))
    
    retrieved = await repo.get(job.id)
    assert retrieved.type == "test"
    # Rollback automático no teardown
```

### Estratégia de Mocks Externos
```python
# httpx_mock para APIs HTTP
async def test_llm_provider_with_mock(httpx_mock):
    httpx_mock.add_response(
        url="https://api.openai.com/v1/chat/completions",
        json={"choices": [{"message": {"content": "OK"}}]}
    )
    
    response = await provider.chat("hello")
    assert response.content == "OK"
```

---

## 4. E2E Tests

### Quando Criar
- Fluxos críticos de usuário
- Integração WhatsApp completa
- Orquestração multi-agente

### Cenários Obrigatórios
| ID | Cenário | Criticidade |
|----|---------|-------------|
| E2E-01 | Receber mensagem → Processar → Responder | Crítico |
| E2E-02 | Criar tarefa via comando natural | Alto |
| E2E-03 | Job em fila → Executar → Completar | Alto |
| E2E-04 | Memory search → Contexto → Resposta | Médio |

### Estrutura
```python
async def test_whatsapp_message_end_to_end(whatsapp_client, db):
    # Simula mensagem recebida
    await whatsapp_client.receive_message(
        from_number="+5511999999999",
        text="Criar lembrete: reunião às 15h"
    )
    
    # Aguarda processamento
    await asyncio.sleep(2)
    
    # Verifica resposta enviada
    sent_messages = whatsapp_client.get_sent_messages()
    assert len(sent_messages) == 1
    assert "lembrete criado" in sent_messages[0].text.lower()
```

---

## 5. Cobertura Mínima

| Componente | Mínimo | Alvo | Crítico |
|------------|--------|------|---------|
| **Backend (geral)** | 85% | 90% | ✅ |
| **Frontend** | 75% | 85% | ✅ |
| **Agents** | 90% | 95% | ✅✅ |
| **Providers** | 90% | 95% | ✅✅ |
| **Orchestrator** | 90% | 95% | ✅✅ |
| **Memory** | 85% | 90% | ✅ |
| **API Routes** | 85% | 90% | ✅ |

**Regra:** Nenhuma PR pode reduzir cobertura total do projeto.

### Comandos
```bash
# Backend
pytest backend/tests/ --cov=backend --cov-fail-under=85 --cov-report=html

# Frontend
npm test -- --coverage --threshold=75

# Verificar linhas não cobertas
coverage html
open htmlcov/index.html
```

---

## 6. Fixtures

### Organização (`conftest.py`)
```python
# Fixtures simples
@pytest.fixture
def sample_user():
    return User(id=1, name="Test", email="test@example.com")

# Fixtures parametrizadas
@pytest.fixture(params=["openai", "gemini", "anthropic"])
def llm_provider(request):
    return get_provider(request.param)

# Fixtures aninhadas
@pytest.fixture
async def db_session(db_engine):
    async with db_engine.begin() as conn:
        yield conn
        await conn.rollback()

# Fixtures de integração
@pytest.fixture
async def whatsapp_client():
    client = WhatsAppClient()
    await client.connect()
    yield client
    await client.disconnect()
```

### Boas Práticas
- Nome descritivo: `db_session`, `llm_provider_mock`
- Escopo adequado: `function` (padrão), `session` (lento)
- Cleanup garantido: usar `yield` + teardown
- Reutilizável: DRY entre testes

---

## 7. Performance Tests

### Quando Criar
- Endpoints de alta frequência
- Loops de processamento em massa
- Queries de banco complexas

### Métricas
| Tipo | Limite | Alerta |
|------|--------|--------|
| API Response | < 200ms | > 100ms |
| Agent Processing | < 2s | > 1s |
| Memory Search | < 500ms | > 300ms |
| Job Execution | < 5s | > 3s |

### Exemplo
```python
import time

def test_memory_search_performance(memory_manager):
    start = time.perf_counter()
    
    results = memory_manager.search("reunião amanhã", limit=10)
    
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"Search took {elapsed:.2f}s (> 0.5s)"
    assert len(results) >= 1
```

---

## 8. Anti-Padrões

### ❌ RUIM
```python
# Teste sem asserção clara
def test_something():
    result = some_function()
    print(result)  # Só imprime, não testa nada

# Teste dependente de ordem
def test_create_user():
    global user_id
    user_id = create_user()  # Outro teste depende disso

# Teste lento (chama API real)
def test_llm_real():
    response = openai.ChatCompletion.create(...)  # Lento e caro
```

### ✅ BOM
```python
# Asersão clara
def test_create_user_returns_id():
    user_id = create_user(name="Test")
    assert isinstance(user_id, int)
    assert user_id > 0

# Isolado
def test_create_user_isolated():
    user_id = create_user(name="Test")
    assert user_id is not None
    # Não depende de estado global

# Mockado
def test_llm_mocked(httpx_mock):
    httpx_mock.add_response(json={"content": "OK"})
    response = llm_provider.chat("hello")
    assert response.content == "OK"
```

---

## 9. KPIs de Qualidade

| Métrica | Meta | Como Medir |
|---------|------|------------|
| **Cobertura** | ≥ 85% | `pytest --cov` |
| **Tempo médio teste** | < 200ms | `pytest --durations` |
| **Flaky tests** | 0 | CI/CD reruns |
| **Bugs em produção** | < 0.1/tarefa | Issue tracking |
| **Regressões** | 0 | E2E suite |

---

## 10. Manutenção de Testes

### Quando Refatorar
- Teste duplicado (> 3 vezes)
- Fixture muito complexa (> 30 linhas)
- Nome não descritivo
- Lento (> 1s sem justificativa)

### Quando Remover
- Teste sem asserção útil
- Teste de implementação (não comportamento)
- Obsoleto (feature removida)

**Regra de Ouro:** *Teste mal escrito é pior que nenhum teste.*
