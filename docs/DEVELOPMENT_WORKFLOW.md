# Development Workflow — OSAI

Este documento descreve o fluxo de desenvolvimento diário para
contribuidores do OSAI.

---

## 1. Setup do Ambiente

### 1.1 Pré-requisitos

- Python 3.12+
- Node.js 20+
- Git
- Docker (opcional, para PostgreSQL em produção)

### 1.2 Clone e Instalação

```bash
git clone https://github.com/prdariomarques-ship-it/ship-it.git
cd ship-it

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements-dev.txt

# Frontend
cd ../frontend
npm ci
```

### 1.3 Variáveis de Ambiente

Copie `.env.example` para `.env` e configure:

```bash
cp backend/.env.example backend/.env
cp docker/.env.example docker/.env
```

---

## 2. Fluxo de Desenvolvimento

### 2.1 Iniciar Trabalho em uma Issue

1. Identifique a Issue no GitHub Project (coluna **Ready** ou **Product Backlog**).
2. Verifique se o Milestone está definido.
3. Verifique se as Labels de Priority, Type, Area e Release estão aplicadas.
4. Crie uma branch a partir de `master`:

```bash
git checkout master
git pull origin master
git checkout -b feature/cap-001-economic-calendar
```

### 2.2 Desenvolvimento

- Implemente a funcionalidade conforme os Acceptance Criteria da Issue.
- Escreva testes para cada novo comportamento.
- Rode o CI localmente antes de commitar:

```bash
# Backend
cd backend
ruff check .
mypy --ignore-missing-imports .
pytest -q

# Frontend
cd frontend
npm run lint
npm test
npm run build
```

### 2.3 Commits

Use mensagens de commit semânticas:

```
feat(cap-001): add economic calendar dashboard

- Implement calendar view with event display
- Add date and country filters
- Integrate with Economic Calendar API
- Add unit tests for calendar service
```

---

## 3. Pull Request

### 3.1 Preparação

Antes de abrir o PR:

```bash
# Garantir que a branch está atualizada
git fetch origin
git rebase origin/master

# Rodar todos os checks
cd backend && ruff check . && pytest -q
cd frontend && npm run lint && npm test && npm run build
```

### 3.2 Abrir PR

1. Push a branch: `git push origin feature/cap-001-economic-calendar`
2. Abra um PR a partir da interface do GitHub.
3. Use o template `.github/PULL_REQUEST_TEMPLATE/pull_request_template.md`.
4. Referencie a Issue: `Closes #11`.
5. Preencha todos os campos do template.

### 3.3 Review

- O PR será revisado por outro contribuidor.
- Resolva todos os comentários antes de solicitar merge.
- CI deve estar verde em todos os checks.

---

## 4. Migrations (Backend)

```bash
cd backend

# Criar nova migration
alembic revision --autogenerate -m "descrição curta"

# Aplicar migrations
alembic upgrade head

# Reverter última migration
alembic downgrade -1

# Verificar drift
alembic check
```

### Regras de Migration

1. Sempre revise o arquivo gerado pelo autogenerate.
2. Para ENUMs do PostgreSQL, crie o tipo explicitamente na migration.
3. Teste upgrade e downgrade.
4. Rode `alembic check` antes de commitar.

---

## 5. Testes

### 5.1 Backend

```bash
cd backend
pytest -q                    # Suite completa
pytest tests/test_cap001.py  # Arquivo específico
pytest -x                    # Parar no primeiro erro
pytest --cov                 # Com coverage
```

### 5.2 Frontend

```bash
cd frontend
npm test                     # Suite completa (Vitest)
npm run e2e                  # End-to-end (Playwright)
```

### 5.3 Convenções de Teste

- Backend: use fixtures de `tests/conftest.py` (`db_engine`, `client`).
- Mocke bordas externas (HTTP clients, providers), nunca a lógica interna.
- Singletons são resetados automaticamente por fixture `autouse`.
- Frontend: Vitest + Testing Library para componentes, Playwright para E2E.

---

## 6. Troubleshooting

| Problema | Solução |
|----------|---------|
| `alembic upgrade head` falha | Verifique `backend/.env` e `DATABASE_URL` |
| `npm ci` falha | Remova `node_modules` e `package-lock.json`, rode `npm install` |
| Tests falham no CI mas passam local | Verifique variáveis de ambiente no GitHub Secrets |
| Migration autogenerate incorreto | Edite manualmente, consulte `MIGRATION_FIX_REPORT.md` |
| Lint falha | `ruff check . --fix` ou `npm run lint -- --fix` |
