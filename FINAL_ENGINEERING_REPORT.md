# Relatório Final de Engenharia — Dario OS

**Data:** 2026-07-16
**Escopo:** Recuperação de infraestrutura, débito técnico, CI/CD, segurança, e integração WhatsApp (OpenWA)
**Commits desta sessão:** `2d4dacb`..`cdc944c` (11 commits, publicados em `origin/master`)

---

## 1. Causa raiz

### 1.1 OpenWA — crash loop (corrigido)

**Arquivo:** `docker/openwa/Dockerfile` (imagem base `openwa/wa-automate:latest`)

O binário `ps` não existe na imagem base (Debian slim). A dependência transitiva `ps-tree` — usada pelo open-wa para limpar processos Chromium órfãos após timeout de página — faz `spawn('ps', ['-A', '-o', 'ppid,pid,stat,comm'])` sem handler de erro anexado ao child process. `ENOENT` vira exceção não tratada, derruba o processo Node inteiro, e o `restart: unless-stopped` do Docker gera um loop infinito antes de qualquer QR code poder ser escaneado (`RestartCount` observado: 98+).

**Evidência:** reproduzido diretamente nos logs do container antes do fix; confirmado que `which ps` retorna vazio na imagem base; identificado o `spawn()` exato em `node_modules/ps-tree/index.js`.

### 1.2 OpenWA — bloqueio "atualize seu navegador" (corrigido)

**Arquivo:** `node_modules/@open-wa/wa-automate/dist/controllers/browser.js` (dentro da imagem, patchado)

A lib sobrescreve incondicionalmente o user-agent da página via CDP (`page.setUserAgent()`) com uma string hardcoded e obsoleta (`Chrome/104.0.0.0`, de `config/puppeteer.config.js`). O WhatsApp Web detecta a inconsistência entre essa string e os Client Hints reais do Chromium 133 instalado, e serve sua página estática de "atualize o navegador" em vez do app real — por isso `window.Debug` nunca aparecia e o QR nunca era gerado.

**Evidência:** reproduzido com scripts Puppeteer isolados e bounded (10-20s cada, nunca esperando indefinidamente): (a) sem nenhum override de UA → QR real aparece; (b) com a string obsoleta → tela de bloqueio; (c) com o UA real do Chrome instalado → **também** tela de bloqueio; (d) com UA real + Client Hints (`userAgentMetadata`) combinando → **ainda** tela de bloqueio. Conclusão provada: o problema é a chamada a `setUserAgent()` em si, não o valor passado.

### 1.3 OpenWA — vazamento de base64 no painel de log (corrigido)

**Arquivo:** `node_modules/@open-wa/wa-automate/dist/controllers/popup/index.html` (dentro da imagem, patchado)

A página de autenticação (`:8002`) despeja o `.data` bruto de toda mensagem de socket no painel de log visível, excluindo só o namespace `"sessionDataBase64"` — não `"qr"`, cujo `.data` é a data URI base64 completa da imagem do QR. A imagem já renderizava corretamente via `.src = message.data` em linha separada; o vazamento era redundante.

### 1.4 OpenWA — falha no envio de mensagens (`isRegularUser is not a function`) (mitigado, causa raiz upstream)

**Arquivo:** `node_modules/@open-wa/wa-automate/dist/lib/wapi.js`, função `getStore()` (linha ~63 no original)

**Cadeia de execução, rastreada e confirmada:**
```
backend/providers/whatsapp/openwa/provider.py: send_text()
  → POST /sendText
    → Client.js: sendText(to, content)
      → WAPI.sendMessage(to, content)  [browser context]
        → chat.sendMessage(message)
          → Store.Chat.modelClass.prototype.sendMessage  [SOBRESCRITO pelo open-wa]
            → window.Store.SendTextMsgToChat(this, ...arguments)
              → função interna do WhatsApp (resolvida via scan do bundle deles)
                → throw: "t.isRegularUser is not a function"
```

**Evidência multi-fonte, não hipótese:**
1. **Runtime direto**: erro reproduzido chamando `/sendText` contra uma conta WhatsApp Business real e pareada; stack trace apontando para `static.whatsapp.net/rsrc.php/.../pt_BR-j/....js` — domínio do WhatsApp, não do open-wa.
2. **Código-fonte do WhatsApp, buscado ao vivo**: `isRegularUser` existe 17 vezes no bundle real deles, como método de instância `Wid` (`n.isRegularUser=function(){return this.isUser()&&!this.isPSA()&&!this.isBot()}`), fortemente associado a `WAWebLidMigrationUtils` — confirma migração ativa do WhatsApp para o sistema de identificadores **LID (Linked ID)**.
3. **Confirmação externa independente**: `whatsapp-web.js` (biblioteca não relacionada) teve o mesmo tipo de falha (`"Lid is missing in chat table"`), corrigida na v1.33.3 deles.
4. **Confirmação no próprio open-wa**: issue [#3322](https://github.com/open-wa/wa-automate-nodejs/issues/3322) (aberta 23/fev/2026, **ainda aberta**) descreve sintoma da mesma família (`SendFile` retorna `false` para `ChatId` terminado em `@lid`). Sem fix em `wapi.js` desde 2024 (dez/2025 foi só reestruturação de pastas).
5. **Mecanismo da corrida, confirmado nos logs**: `WAWebCollections` (módulo que popula `window.Store`) depende de ~45 sub-coleções internas do WhatsApp (`WAWebChatCollection`, `WAWebContactCollection`, etc.) carregadas de forma assíncrona; o `require()` síncrono do open-wa corre contra esse carregamento. Quando a corrida favorece o open-wa, o override problemático se instala; quando não, `chat.sendMessage` permanece o `sendMessage` nativo do WhatsApp — que já é compatível com LID.
6. **Prova por reversão**: com o override desativado, 6+ envios reais consecutivos tiveram sucesso, todos com ID de resposta no formato `@lid` (ex.: `true_208095477264614@lid_3EB0951AC7FB27AEA1FBA4_out`).

**Limite da evidência (honestidade forense)**: não foi capturado um dump variável-por-variável do objeto exato (`this`, `contact`, `t`) no instante preciso do `throw` dentro de `SendTextMsgToChat` — a instrumentação foi escrita (`FORENSIC`/`FORENSIC2`, patches temporários e revertidos) mas a corrida de módulos nunca reinstalou o override problemático numa tentativa subsequente com a instrumentação ativa. A causa estrutural (migração LID, função incompatível) está provada por 5 fontes independentes; o dump variável-a-variável do momento exato do crash não foi obtido.

### 1.5 Corrida secundária, não corrigida — `Store.Contact` undefined em chat sem histórico

Mesma classe de corrida do item 1.4, mas afetando `Store.Contact` em vez de `Store.Chat`. Só se manifesta no **primeiro** envio a um chat sem histórico prévio (`chat.msgs.models.length == 0`); desaparece sozinha depois de 1 mensagem bem-sucedida. Reproduzido 3x consecutivas logo após um pareamento novo.

---

## 2. Mudanças implementadas

| # | Mudança | Tipo |
|---|---|---|
| 1 | Instalar `procps` na imagem do openwa (fornece `ps`) | Fix de causa raiz |
| 2 | Remover repo apt do Chrome com chave expirada (bloqueava `apt-get update`) | Fix de causa raiz |
| 3 | Só chamar `setUserAgent()` quando `customUserAgent` for explicitamente configurado | Fix de causa raiz |
| 4 | Excluir namespace `"qr"` do dump de log da página de autenticação | Fix de causa raiz |
| 5 | Desativar por padrão o override `Store.Chat.modelClass.prototype.sendMessage`, via feature flag `WA_ENABLE_LEGACY_SENDMESSAGE_OVERRIDE` | Mitigação de causa raiz upstream (WhatsApp LID) |
| 6 | Remoção de código morto: `backend/performance/*`, `backend/observability/{performance_middleware,grafana_dashboard}.py`, `frontend/src/utils/performance.ts` | Débito técnico |
| 7 | CI: type checking (mypy, não existia), testes de frontend (nunca rodavam), validação do docker-compose, lint/audit report-only | CI/CD |
| 8 | 27 erros de mypy corrigidos, incluindo 2 bugs reais (`Qdrant.vectors_count` inexistente, `Gauge.record()` → `.set()`) | Correção de bug |
| 9 | `pypdf` 5.9.0→6.14.x (31 CVEs → 0); `next`/`eslint-config-next` 14.2.21→14.2.35 (crítica eliminada) | Segurança |
| 10 | 5 documentos já auto-marcados `DEPRECATED` removidos; `PROJECT_STATUS.md` com números de 4 dias atrás atualizados/sinalizados | Documentação |
| 11 | Migration MIG-001 com índice duplicado corrigida | Fix de bug |

---

## 3. Arquivos modificados (por commit)

```
2d4dacb  docker/openwa/Dockerfile (novo); docker/docker-compose.yml
58b2ed2  backend/alembic/versions/daa5cef5165c_...py; frontend/package-lock.json
e42d566  backend/utils/config.py
e928f95  .github/workflows/ci.yml; 24 arquivos backend/ (mypy/lint fixes)
789f6dd  backend/requirements.txt; frontend/package.json; frontend/package-lock.json; .github/workflows/ci.yml
45d4ed4  5 arquivos removidos; DOCUMENTATION_INDEX.md; PROJECT_STATUS.md; docs/architecture.md
4dff2c3  DOCUMENTATION_INDEX.md; PROJECT_STATUS.md; docs/architecture.md (follow-up de staging)
9f24578  backend/tests/test_monitoring_integration.py
cad63e0  docker/openwa/Dockerfile
81dcca7  docker/openwa/Dockerfile
cdc944c  docker/openwa/Dockerfile
```

---

## 4. Evidência de teste

| Verificação | Resultado |
|---|---|
| Suíte de backend (host, = CI real) | **758/758 passed**, rodado 3x de forma independente ao longo da sessão, resultado idêntico todas as vezes |
| Suíte de backend (container de produção) | 753/758 (as 5 restantes são artefato do filesystem restrito do container — confirmadas passando no ambiente equivalente ao CI real) |
| Suíte de frontend (Vitest) | **108/108 passed** |
| Build de produção (Next.js) | Sucesso, sem erros de tipo |
| `mypy` | 0 erros, 263 arquivos |
| `ruff check` | 0 erros |
| `sendText` (WhatsApp real, pareado) | **6/6 sucessos consecutivos** após o fix, IDs de resposta em formato `@lid` |
| Persistência de sessão | Confirmada 3x — restart do container sem exigir novo QR, chegando em `"Client is ready"` |
| Migrations (do zero) | 11/11 aplicadas, 22 tabelas, 16 FKs íntegras |

---

## 5. Evidência de regressão

- Nenhuma queda no número de testes passando em nenhum momento da sessão.
- Remoção de código morto: 856→758 testes de backend é **esperado** (removeu os testes dos módulos deletados, não regressão).
- `sendImage`/`sendFile`/`sendButtons`: confirmado **não ser regressão** — `WAPI.createTemporaryFileInput` e `WAPI.sendButtons` não existem em nenhum lugar do `wapi.js` desta versão do open-wa, independente de qualquer patch feito nesta sessão (checado via `grep`, 0 ocorrências).
- Stack completa (12 serviços): 0 restarts em todos os containers na checagem mais recente.

---

## 6. Débito técnico remanescente

1. **Envio de mídia/botões (`sendImage`, `sendFile`, `sendButtons`) não funcional** — funções ausentes no `wapi.js` desta versão do open-wa, não relacionado a este trabalho.
2. **Corrida de `Store.Contact`** no primeiro envio a chat vazio — sem fix dedicado, mitigação natural (some após 1ª mensagem).
3. **Restarts consecutivos do openwa tendem a invalidar a sessão pareada** — padrão observado repetidamente; evitar restarts desnecessários em produção.
4. **`SingletonLock` órfão do Chromium** após recreate rápido do container — precisou de limpeza manual 3x nesta sessão; sem fix automatizado ainda.
5. **Formatação (`ruff format`)** nunca aplicada a 206 arquivos do backend — rodando só como report no CI.
6. **4 vulnerabilidades altas + 1 moderada remanescentes no `next`** — só fecham com upgrade de major (15.5.16+/16.x), não seguro de automatizar sem QA/E2E dedicado.
7. **Cluster de 5 documentos de governança sobrepostos**, sem vencedor auto-declarado — decisão editorial pendente.
8. **Branch `claude/dario-os-platform-gcg6i2`** — iniciativa de produto paralela (DRT Runtime), 48 commits, decisão de adoção pendente.
9. **Evidência forense incompleta** do crash `isRegularUser` (seção 1.4) — causa estrutural provada, dump variável-a-variável do momento exato não capturado.

---

## 7. Prontidão para produção

| Área | Nota | Observação |
|---|---|---|
| Infraestrutura/Docker | 9/10 | 12/12 serviços saudáveis, 0 restarts, migrations íntegras |
| Backend | 9/10 | 758 testes, mypy limpo, 0 vulnerabilidades |
| Frontend | 8/10 | 108 testes, build limpo; vulnerabilidades altas remanescentes no Next |
| CI/CD | 8/10 | Cobertura completa; formatação/audit ainda report-only |
| WhatsApp (texto) | 8/10 | Funcional e validado com evidência real |
| WhatsApp (mídia/botões) | 2/10 | Não implementado nesta versão do open-wa |
| Documentação | 7/10 | Duplicatas óbvias removidas; cluster de governança pendente |

**Nota geral: 78/100.**

---

## 8. Próximos marcos recomendados (por prioridade)

1. Decidir sobre mídia/botões no WhatsApp: aceitar a limitação, ou investir em contornar (ex.: implementar `sendImage`/`sendFile` via outro mecanismo do próprio `WAPI`, se existir um equivalente funcional).
2. Automatizar a limpeza do `SingletonLock` órfão no boot do container `openwa` (mitiga um dos poucos pontos de fragilidade operacional remanescentes).
3. Resolver o cluster de documentos de governança (5 candidatos, sem vencedor claro).
4. Decisão de produto sobre a branch `claude/dario-os-platform-gcg6i2` (DRT Runtime).
5. Migração major do Next.js (14→15/16), com E2E dedicado, para fechar as vulnerabilidades altas remanescentes.
6. Reformatação do backend (`ruff format`) como iniciativa isolada, dado o volume (206 arquivos).
