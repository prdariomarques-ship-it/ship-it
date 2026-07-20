# Checklist de Migração — OpenWA → WhatsApp Cloud API (Official)

**Status atual: OpenWA continua sendo o provider de produção.** Este documento
é o roteiro de onboarding + validação a seguir antes de trocar
`WHATSAPP_PROVIDER=openwa` → `official`. Nenhum passo aqui troca o provider em
produção — a troca só deve acontecer depois que todos os itens estiverem
marcados.

Contexto: o provider `official` (`backend/providers/whatsapp/official/provider.py`)
já está implementado — envio (5 métodos), parsing de webhook, verificação de
assinatura HMAC-SHA256. O handshake de verificação GET exigido pela Meta
(`GET /webhooks/whatsapp`) foi implementado no commit `b50b417`. O que falta é
inteiramente onboarding do lado da Meta (ação externa, fora do alcance do
Claude Code) + validação ponta a ponta antes do corte.

## 1. Criar o Meta App

- [ ] Criar conta/acessar [Meta for Developers](https://developers.facebook.com/)
- [ ] Criar um novo App, tipo **Business**
- [ ] Anotar o **App ID** e o **App Secret** (usado depois em `OFFICIAL_APP_SECRET`)

## 2. Configurar o WhatsApp Business

- [ ] No painel do App, adicionar o produto **WhatsApp**
- [ ] Criar (ou vincular) uma **WhatsApp Business Account (WABA)**
- [ ] Adicionar/confirmar um número de telefone de teste ou de produção
- [ ] Confirmar que o número está no status **Connected**/verificado

## 3. Obter as credenciais

- [ ] **`OFFICIAL_ACCESS_TOKEN`** — gerar um token de acesso permanente
      (System User token, não o token temporário de 24h que aparece por
      padrão no playground) com permissão `whatsapp_business_messaging`
- [ ] **`OFFICIAL_PHONE_NUMBER_ID`** — copiar do painel WhatsApp > API Setup
      (é o ID interno do número, não o número de telefone em si)
- [ ] **`OFFICIAL_WEBHOOK_VERIFY_TOKEN`** — definir você mesmo (qualquer
      string secreta seguem, ex. gerada com `openssl rand -hex 32`) — vai ser
      usada nos dois lados (painel da Meta e `.env`)
- [ ] (Recomendado) Copiar o **App Secret** também, para `OFFICIAL_APP_SECRET`
      — habilita a verificação de assinatura HMAC dos webhooks
- [ ] Preencher as 4 chaves em `docker/.env` (nunca commitar — já está no
      `.gitignore`)

## 4. Configurar a URL do webhook

- [ ] Confirmar que o backend está acessível publicamente via HTTPS na URL de
      produção (o Caddy já serve `/webhooks/whatsapp` — confirmar que a rota
      não está bloqueada por nenhum proxy/firewall)
- [ ] No painel do App > WhatsApp > Configuration, preencher:
  - **Callback URL**: `https://<seu-dominio>/api/webhooks/whatsapp`
    (confirmar o prefixo `/api` — ver `main.py`, `include_router(webhooks_router, prefix=prefix)`)
  - **Verify Token**: o mesmo valor de `OFFICIAL_WEBHOOK_VERIFY_TOKEN`
- [ ] Clicar em **Verify and Save**

## 5. Completar a verificação do webhook

- [ ] Confirmar no log do backend que a Meta chamou `GET /webhooks/whatsapp`
      com `hub.mode=subscribe` e recebeu `200` de volta com o `hub.challenge`
      ecoado (é exatamente esse fluxo que o clique em "Verify and Save" do
      passo 4 dispara — se falhar, o painel mostra erro imediatamente e não
      salva a configuração)
- [ ] Se falhar: conferir se `OFFICIAL_WEBHOOK_VERIFY_TOKEN` está idêntico
      nos dois lados (copy/paste, sem espaço extra) e se a URL está
      respondendo publicamente (`curl` externo, não só de dentro da rede
      Docker)
- [ ] No painel, assinar (subscribe) o app aos campos de webhook `messages`
      (mínimo necessário; opcionalmente `message_status` para confirmações de
      entrega)

## 6. Validar a verificação de assinatura HMAC

- [ ] Confirmar `OFFICIAL_APP_SECRET` preenchido no `.env`
- [ ] Enviar uma mensagem de teste (ver passo 7) e conferir no log do backend
      que `OfficialProvider.verify_signature()` está sendo chamado e
      retornando `True` (o header `X-Hub-Signature-256` chega em toda entrega
      real da Meta)
- [ ] (Opcional, mais rigoroso) Temporariamente alterar 1 caractere do
      `OFFICIAL_APP_SECRET` local e confirmar que o webhook passa a responder
      `401 Invalid webhook signature` — depois reverter para o valor certo

## 7. Enviar e receber uma mensagem real

Ainda com `WHATSAPP_PROVIDER=openwa` em produção — este teste deve ser feito
**isolado**, sem afetar o tráfego de produção (rodar o backend localmente com
`WHATSAPP_PROVIDER=official` e as credenciais reais, ou usar um ambiente de
staging/sandbox à parte):

- [ ] **Envio**: `POST /api/whatsapp/send-text` para um número de teste
      autorizado (a Meta restringe envio a números de teste registrados
      enquanto o app está em modo Development) — confirmar entrega real no
      WhatsApp do destinatário
- [ ] **Recebimento**: responder a partir do WhatsApp real → confirmar que o
      webhook chega em `POST /webhooks/whatsapp`, é parseado corretamente
      (`OfficialProvider.parse_webhook`) e vira uma `Message` persistida com
      `direction=INBOUND`
- [ ] Confirmar que a resposta automática (`AUTO_REPLY_ENABLED=true`) dispara
      corretamente pelo pipeline padrão (webhook → job queue → AI
      Orchestrator → resposta) sem exigir nenhuma mudança de código — essa é
      a prova de que a abstração de provider está funcionando

## 8. Rodar os smoke tests ponta a ponta

- [ ] `pytest -q` completo (suíte já cobre `official` via
      `test_whatsapp_provider_compatibility.py` e `test_webhook_security.py`
      — deve continuar 100% verde)
- [ ] Repetir manualmente o roteiro de `WHATSAPP_VALIDATION.md` (mesmo
      formato: gateway direto + round-trip via API) mas apontando pro
      `official` em vez do `openwa`
- [ ] Validar `/health/ready` reportando `whatsapp: ok` com o provider
      `official` ativo
- [ ] Confirmar métricas (`darioos_whatsapp_provider_requests_total{provider="official"}`,
      `darioos_whatsapp_session_status{provider="official"}`) aparecendo no
      Grafana

## 9. Corte para produção

Só depois de todos os itens acima:

- [ ] Trocar `WHATSAPP_PROVIDER=official` em `docker/.env` (produção)
- [ ] `docker compose up -d --no-deps backend` (reinício isolado, mesmo
      padrão usado no deploy do Next.js 16 — ver `DEPLOYMENT_REPORT.md`)
- [ ] Confirmar `/health/ready` e logs pós-restart sem erro
- [ ] Observar por um período (recomendado: 24h) antes de considerar o
      OpenWA desativável

## Procedimento de rollback (OpenWA)

A troca de provider é **configuração, não código** — é o ponto central do
padrão Factory/Strategy documentado em
`backend/providers/whatsapp/README.md`. Rollback é deliberadamente barato:

1. Reverter `WHATSAPP_PROVIDER=official` → `WHATSAPP_PROVIDER=openwa` em
   `docker/.env`
2. `docker compose up -d --no-deps backend`
3. Confirmar `/health/ready` reportando `whatsapp: ok` novamente com o
   provider OpenWA
4. Nenhuma migração de banco, nenhuma mudança de schema, nenhum dado
   perdido — `Message`/`Contact` já são agnósticos de provider

**Gatilhos para rollback** (qualquer um destes, durante ou logo após o corte):

- Webhook parando de receber mensagens reais (nenhuma `Message` nova
  persistida apesar de mensagens sendo enviadas pelo WhatsApp real)
- Falha de verificação de assinatura em mensagens legítimas (falso negativo
  do HMAC — indicaria `OFFICIAL_APP_SECRET` errado ou mudança não
  documentada da Meta no esquema de assinatura)
- `/health/ready` reportando `whatsapp: error` de forma persistente
- Taxa de erro elevada em `darioos_whatsapp_provider_requests_total{provider="official",status="error"}`
- Qualquer mensagem de saída não entregue sem erro reportado (repetir o
  achado do `WHATSAPP_VALIDATION.md` — sucesso silencioso incorreto)

Como o OpenWA continua instalado e configurado (não é removido neste ciclo),
o rollback é uma troca de variável de ambiente + restart, sem necessidade de
reconstruir imagem nem reverter commit.

## Referências

- `backend/providers/whatsapp/README.md` — contrato do Provider e regra de
  ouro (trocar de gateway é configuração, não código)
- `backend/providers/whatsapp/official/provider.py` — implementação atual
- `backend/webhooks/router.py` — handshake GET + rota POST de recebimento
- `WHATSAPP_VALIDATION.md` — roteiro de validação usado no OpenWA, modelo
  para repetir com o `official`
- `CHANGELOG.md` (`[Unreleased]` → `Adicionado`) — commit `b50b417`,
  handshake de verificação implementado
