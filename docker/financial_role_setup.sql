-- ⚠️ PROPOSTA — NÃO APLICADO. Não execute este arquivo contra nenhum banco,
-- incluindo o da VPS, sem autorização explícita de um deployment window.
-- Nenhuma credencial foi criada; a senha abaixo é um placeholder a ser
-- substituído (e gerado/guardado fora deste repositório) no momento em
-- que a aplicação for de fato autorizada.
--
-- Objetivo (revisão, ponto 4): o pool de conexão menor do financial-worker
-- (docker-compose.financial.yml) limita CONCORRÊNCIA por processo, mas os
-- dois serviços ainda compartilham o mesmo usuário Postgres do backend
-- principal — ou seja, HOJE o worker financeiro TEM permissão de ler e
-- escrever em `jobs` e em qualquer outra tabela do domínio WhatsApp,
-- simplesmente porque usa a mesma credencial. Isso não é isolamento de
-- permissão, é isolamento lógico por convenção de código (o worker nunca
-- importa repositories/job.py — ver worker.py's docstring) — que é real,
-- mas não é a mesma garantia que uma role restrita no banco.
--
-- Este script cria essa segunda garantia, em camada adicional (não troca
-- nada do setup existente, não altera a role do backend principal, não
-- remodela o schema):
--
--   1. Uma role `financial_worker` nova, LOGIN, sem SUPERUSER/CREATEDB/
--      CREATEROLE.
--   2. GRANT explícito de SELECT/INSERT/UPDATE somente em `financial_jobs`
--      (a tabela deste pacote — ver backend/investments/models.py).
--      Sem DELETE (o worker nunca apaga linhas) e sem GRANT em nenhuma
--      sequência/tabela fora dessa.
--   3. REVOKE explícito (redundante com o padrão "nada concedido = nada
--      permitido" do Postgres, mas escrito aqui para deixar a intenção
--      auditável e não dependente de nunca ter sido concedido por engano
--      no futuro) de qualquer privilégio em `jobs` e nas demais tabelas do
--      domínio WhatsApp.
--   4. Um `ALTER DEFAULT PRIVILEGES` NÃO é incluído de propósito: isso
--      afetaria tabelas futuras criadas por outros serviços, o que está
--      fora do escopo desta mudança. Qualquer tabela nova do domínio
--      WhatsApp fica automaticamente SEM acesso para esta role (o padrão
--      do Postgres), sem precisar de um REVOKE explícito por tabela — mas
--      se uma tabela nova for criada já com GRANT amplo (ex.: `GRANT ALL
--      ON ALL TABLES IN SCHEMA public TO <algum grupo>` em algum script
--      futuro), ela pode acabar incluindo esta role também; revisar isso
--      é parte do checklist de aplicação, não algo que este script possa
--      garantir sozinho.
--
-- Pré-requisito para rodar isto com segurança (quando autorizado): saber
-- os nomes exatos de todas as tabelas do domínio WhatsApp no banco de
-- destino. Os nomes abaixo (`jobs`, mais os que a introspecção abaixo
-- lista) devem ser confirmados contra o schema real antes de aplicar —
-- não foram confirmados aqui porque isso exigiria uma conexão com o
-- banco real, que esta etapa não autoriza.

-- Introspecção recomendada ANTES de aplicar (somente leitura, roda sob a
-- credencial atual do backend, sem criar nada):
--   SELECT tablename FROM pg_tables WHERE schemaname = 'public';
-- Confirme que a lista abaixo em REVOKE cobre tudo que não é
-- `financial_jobs`, `alembic_version` (necessário só para migração, não
-- para o worker) ou outra tabela já conhecidamente própria deste pacote.

-- ───────────────────────────── 1. Role ──────────────────────────────────

CREATE ROLE financial_worker WITH
    LOGIN
    PASSWORD 'REPLACE_ME_BEFORE_APPLYING'  -- gerar fora do repo; nunca commitar o valor real
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    CONNECTION LIMIT 5;  -- alinhado ao pool pequeno do serviço (DB_POOL_SIZE+DB_MAX_OVERFLOW)

-- ───────────────────────── 2. Permissões mínimas ────────────────────────

GRANT CONNECT ON DATABASE darioos TO financial_worker;
GRANT USAGE ON SCHEMA public TO financial_worker;

GRANT SELECT, INSERT, UPDATE ON TABLE financial_jobs TO financial_worker;
-- A sequência do id autoincrement também precisa de USAGE para INSERT
-- funcionar — ajustar o nome se diferente do padrão gerado pelo Alembic:
GRANT USAGE, SELECT ON SEQUENCE financial_jobs_id_seq TO financial_worker;

-- ────────────────────── 3. Negação explícita (WhatsApp) ─────────────────
-- Redundante com o padrão (nada concedido = nada permitido), mas explícito
-- e auditável. Ajustar esta lista para o conjunto REAL de tabelas do
-- domínio WhatsApp confirmado via a introspecção acima antes de aplicar.

REVOKE ALL ON TABLE jobs FROM financial_worker;
-- REVOKE ALL ON TABLE <outras tabelas do domínio WhatsApp aqui> FROM financial_worker;

-- ─────────────────────── 4. Verificação (após aplicar) ──────────────────
-- Prova viva de que a role não lê nem escreve fora de financial_jobs —
-- rodar como um usuário com permissão de SET ROLE ou conectando
-- diretamente como financial_worker:
--
--   SET ROLE financial_worker;
--   SELECT * FROM jobs LIMIT 1;             -- esperado: ERRO permission denied
--   INSERT INTO jobs (id) VALUES (999999);  -- esperado: ERRO permission denied
--   SELECT * FROM financial_jobs LIMIT 1;   -- esperado: OK (lista vazia ou linhas)
--   RESET ROLE;
--
-- Esse bloco de verificação deve ser executado manualmentes e seu
-- resultado (os três erros/sucessos esperados) registrado no PR/changelog
-- de aplicação — não há como este script se autoverificar sem já estar
-- aplicado contra um banco real, o que esta etapa não autoriza.

-- ─────────────── 5. Mudança correspondente em DATABASE_URL ──────────────
-- Quando aplicado, docker-compose.financial.yml's DATABASE_URL passa a
-- usar esta role em vez da credencial do backend principal:
--   DATABASE_URL: postgresql+asyncpg://financial_worker:<senha real, fora do repo>@postgres:5432/darioos
-- Isso NÃO foi alterado no compose neste commit — o compose continua
-- usando a credencial do backend até este script ser revisado e aplicado
-- por alguém com acesso ao banco de produção, para não deixar o serviço
-- apontando para uma role que ainda não existe.
