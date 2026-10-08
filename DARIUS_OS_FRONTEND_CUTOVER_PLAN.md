# Darius OS — Plano de troca e reversão SOMENTE do frontend

Escopo: troca da imagem do serviço `frontend` no `darioos-evolution`, com
reversão garantida. Não toca backend, WhatsApp, banco ou qualquer outro
serviço. Não usa o Compose genérico do repositório (`docker/docker-compose.yml`,
projeto `darioos`) como fonte de verdade — serve só de referência estrutural,
citada explicitamente onde usada. A fonte de verdade é a configuração real
confirmada na VPS em 08/10/2026, abaixo.

**Nenhuma implantação foi executada.** Este documento prepara o plano e o
artefato candidato; a execução na VPS depende do operador e dos 3 pontos
pendentes na seção "O que falta".

## 1. Configuração real confirmada (VPS, 08/10/2026)

| Campo | Valor |
|---|---|
| Projeto Compose | `darioos-evolution` |
| Serviço | `frontend` |
| Nome do container | `darioos-evolution-frontend-1` |
| Estado atual | running / healthy |
| Arquivo Compose | `/opt/chroma-migration-20260927/app.compose.prepared.json` |
| Diretório | `/opt/chroma-migration-20260927` |
| Rede | `darioos-evolution_darioos` |
| Aliases na rede | `frontend`, `darioos-evolution-frontend-1` |
| Porta | `3000/tcp` interna, sem publicação no host |
| Volumes/mounts | nenhum |
| Restart policy | `unless-stopped` |
| Limites | 512 MiB, 0,75 CPU |
| Plataforma | `linux/amd64` |
| Healthcheck (tempos) | intervalo 30s, timeout 5s, início 30s, 3 tentativas |
| Imagem atual (local, imutável) | `sha256:23357543fb50fd2b4e7c94454f80c85e214093f1e9cee53b44fd11376098e84a` |

## 2. O que falta para completar o serviço no Compose (só isto — o resto já está confirmado acima)

1. **`image`/`build`/`pull_policy`/dependências**: não sei se
   `app.compose.prepared.json` define este serviço via `image: <registro>/<repo>:<tag>`
   (pull de um registro) ou via `build: { context, dockerfile }` (build local
   no host da VPS). Isso decide como a nova imagem é referenciada após a troca
   e se existe `pull_policy` (ex.: `never`/`if_not_present`, comum quando a
   imagem só existe localmente, carregada via `docker load`). Também não sei
   se `frontend` declara `depends_on` com alguma condição (ex.:
   `condition: service_healthy` no backend) — isso importa pra saber se um
   `up -d --no-deps frontend` isolado (passo central deste plano, pra não
   tocar outros serviços) é seguro ou se vai brigar com uma dependência
   declarada.
2. **Probe sanitizada do healthcheck**: tenho os tempos (30s/5s/30s/3), mas
   não o comando `test:` real. O Compose genérico do repositório tem um
   achado documentado e relevante aqui (`docker/docker-compose.yml`, serviço
   `frontend`): o servidor standalone do Next.js escuta em `$HOSTNAME`, não
   em `localhost`/`127.0.0.1` — testei isso agora mesmo contra a imagem
   candidata (seção 4) e confirmei: `wget` contra `$(hostname):3000/`
   funciona, contra `localhost:3000/` dá "connection refused" mesmo com o
   app no ar. Se a probe real da VPS usa `localhost`, ela só está passando
   hoje por algum outro motivo (porta publicada, rede diferente, ou um
   healthcheck de nível de proxy) que preciso confirmar — não vou presumir
   que a probe real é a do repositório genérico.
3. **Roteamento `/api` → backend e interface → `frontend:3000`**: preciso do
   trecho sanitizado (service block ou Caddyfile/labels equivalente) do
   componente que faz esse roteamento na VPS — gateway/reverse proxy. O
   Compose genérico do repositório faz isso via Caddy
   (`docker/caddy/Caddyfile`): `handle /api/* { reverse_proxy backend:8000 }`
   e `handle { reverse_proxy frontend:3000 }` (catch-all). É a referência de
   como ESSE código espera ser roteado, mas não presumo que
   `darioos-evolution` usa Caddy ou esse layout exato — preciso confirmar o
   equivalente real antes do corte, porque trocar só a imagem do frontend
   sem saber como o tráfego chega até ela é o jeito mais fácil de produzir
   um "healthy" que não serve nada de fora.

## 3. Fragmento de Compose — somente o serviço `frontend`, com os campos já confirmados

Não é o Compose genérico do repositório. É o serviço isolado, construído só
com dados reais confirmados na seção 1; os 3 campos pendentes da seção 2 estão
marcados explicitamente, não inventados.

```yaml
services:
  frontend:
    # PENDENTE (ver seção 2.1): image: <registro>/<repo>:<tag>  OU  build: {...}
    # PENDENTE (ver seção 2.1): pull_policy
    container_name: darioos-evolution-frontend-1
    restart: unless-stopped
    platform: linux/amd64
    networks:
      darioos-evolution_darioos:
        aliases:
          - frontend
          - darioos-evolution-frontend-1
    expose:
      - "3000"
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.75"
    healthcheck:
      # PENDENTE (ver seção 2.2) — candidato testado nesta sessão contra a
      # imagem candidata, funciona (ver seção 4); confirmar se é o mesmo
      # usado hoje antes de aplicar:
      test: ["CMD-SHELL", "wget --quiet --tries=1 --spider http://$$(hostname):3000/ || exit 1"]
      interval: 30s
      timeout: 5s
      start_period: 30s
      retries: 3
    # PENDENTE (ver seção 2.1): depends_on, se houver

networks:
  darioos-evolution_darioos:
    external: true
```

Nenhum volume declarado (confirmado: nenhum existe hoje). Nenhuma porta
publicada no host (confirmado: 3000/tcp só interna).

## 4. Imagem candidata final — preparada e preservada nesta sessão

**Origem:** commit `c0ff149` de `frontend/darius-os-visual-prod-base` —
Next.js 16.3.6, Sidebar/branding reconciliados com `master`, bug de foco
mobile→desktop corrigido, `.dockerignore` adicionado. Buildada com o
`frontend/Dockerfile` do repositório **sem nenhuma alteração** (diff
verificado abaixo).

**Identificação imutável (ID local de imagem, mesmo formato da imagem atual
da seção 1):**
```
sha256:6e245ad3f7b5b1b5098ad26a3eed8814941ca30ae8b404473c6c8dcaf088377d
```

### Adaptação de certificado usada só para construir esta imagem neste sandbox

Este ambiente de execução intercepta TLS de saída com um proxy que
containers Docker não alcançam nem confiam por padrão (documentado em
`/root/.ccr/README.md`, seção "docker build"), causando
`SELF_SIGNED_CERT_IN_CHAIN` no `npm ci` dentro do container. A VPS de
produção não tem esse proxy e não precisa de nada disto.

Para construir a imagem aqui, usei uma variante **descartável, nunca
commitada** do Dockerfile (`Dockerfile.sandboxtest`), que differia do
Dockerfile real **apenas no estágio `deps`** (adicionando
`NODE_EXTRA_CA_CERTS` apontando pra uma cópia temporária do bundle de CA do
sandbox, só para o `npm ci` conseguir baixar pacotes). Verifiquei por diff
que os estágios `builder` e `runner` — os únicos cujo conteúdo sobrevive na
imagem final — são **byte a byte idênticos** ao `frontend/Dockerfile` real
(`diff` entre os dois a partir de `FROM node:20-alpine AS builder`: saída
vazia, exit code 0). Depois confirmei por `docker history --no-trunc` na
imagem final que nenhuma camada do estágio `deps` aparece nela, e que não há
nenhuma referência a `sandbox`, `ca-bundle` ou `NODE_EXTRA_CA_CERTS` no
histórico — nenhum certificado ou segredo do sandbox entra no artefato
distribuído. Os arquivos descartáveis (`Dockerfile.sandboxtest`, a cópia da
CA) foram apagados ao final; não foram commitados.

### Evidência de build e smoke test (contra a imagem candidata, porta de teste isolada)

```
npm run build dentro do container: 37 rotas, mesmo conjunto de sempre, sem erro de TypeScript/lint.

GET /                → 200, contém "Darius OS"
GET /login            → 200
GET /sw.js            → 200, content-type application/javascript
GET /admin/briefing    → 200 (shell protegido; guard roda no client)
GET /pessoal           → 200

Probe de healthcheck candidata, testada de dentro do container:
  wget http://$(hostname):3000/   → OK
  wget http://localhost:3000/     → FALHOU (connection refused) — confirma
                                     o mesmo gotcha documentado no Compose
                                     genérico do repositório.
```

Nenhum serviço existente foi tocado durante o teste (container isolado,
porta de teste só local, removido ao final).

### Artefato portátil (para não depender de build na VPS)

**Não presumo que a VPS tenha memória suficiente pra rodar `npm run
build`/Turbopack** (os 512 MiB declarados são o limite de *runtime* do
container, não necessariamente o headroom de build do host, e builds
Next.js costumam exigir bem mais que isso durante a compilação). Por isso,
o plano é construir a imagem fora da VPS (como foi feito aqui) e
**transferir o artefato já pronto**, em vez de rodar `docker compose build`
lá.

- Exportada via `docker save | gzip`: `darius-os-frontend-c0ff149.tar.gz`
  (≈ 70 MB).
- Checksum do tarball (integridade de transferência):
  ```
  bf54023a6e64293a602162e761e90f504c80ef14ac0da344a718c2d1c00eeb6a
  ```
- Round-trip verificado nesta sessão: removi a imagem local, recarreguei só
  a partir do tarball (`docker load -i ...`) e o ID resultante bateu
  exatamente com o ID original acima — confirma que o tarball reproduz a
  imagem fielmente, sem corrupção. Testei `/` novamente após o reload: 200.
- Entregue ao usuário junto com este documento.

## 5. Procedimento de troca (frontend-only) — a executar pelo operador na VPS

Nenhum destes passos foi executado por mim; dependem de acesso à VPS que
esta sessão não tem, e dos 3 pontos pendentes (seção 2) para os comandos
exatos de `image:`/`depends_on`/probe.

1. Transferir `darius-os-frontend-c0ff149.tar.gz` para a VPS (scp/rsync) e
   conferir o checksum (`sha256sum` deve bater com o valor acima).
2. **Reter a imagem atual antes de qualquer mudança** — independente de
   `image:`/`build:` na seção 2.1:
   ```
   docker tag sha256:23357543fb50fd2b4e7c94454f80c85e214093f1e9cee53b44fd11376098e84a \
     darius-os-frontend:rollback-20261008
   ```
   Isso garante que a reversão (seção 6) nunca depende de reconstruir nada
   ou de um registro externo estar disponível.
3. Carregar a imagem candidata: `docker load -i darius-os-frontend-c0ff149.tar.gz`
   e confirmar que o ID carregado é `sha256:6e245ad3f7b5b1b5098ad26a3eed8814941ca30ae8b404473c6c8dcaf088377d`.
4. Atualizar **somente** o campo `image` do serviço `frontend` em
   `app.compose.prepared.json` para apontar pra essa imagem (por tag local
   ou pelo ID). Nenhum outro serviço do arquivo é tocado.
5. `docker compose -f app.compose.prepared.json up -d --no-deps frontend`
   — o `--no-deps` é o que garante que só o frontend é recriado.
6. Acompanhar `docker compose -f app.compose.prepared.json ps frontend`
   até `healthy` (com os tempos da seção 1, até ~2 min).
7. Smoke test real a partir da rede interna (porta 3000 não é publicada):
   `docker exec darioos-evolution-frontend-1 wget -qO- http://$(hostname):3000/login`
   e, uma vez confirmado o roteamento da seção 2.3, o mesmo smoke pela URL
   pública (`/`, `/login`, `/api/...` continuando a bater no backend).

## 6. Reversão (frontend-only)

1. Repor o campo `image` do serviço `frontend` em `app.compose.prepared.json`
   para `darius-os-frontend:rollback-20261008` (criada no passo 2 da seção 5)
   — ou, equivalentemente, para o ID original
   `sha256:23357543fb50fd2b4e7c94454f80c85e214093f1e9cee53b44fd11376098e84a`.
2. `docker compose -f app.compose.prepared.json up -d --no-deps frontend`.
3. Confirmar `healthy` de novo pelos mesmos passos 6–7 da seção 5.
4. Sem risco de perda de dado: o serviço não tem volumes (confirmado na
   seção 1), então não há estado para recuperar além do container em si.

## 7. Declarado — não feito nesta entrega

- Nenhum comando das seções 5 e 6 foi executado contra a VPS.
- Backend, WhatsApp, banco e qualquer outro serviço não foram tocados.
- Os 3 pontos da seção 2 continuam pendentes de confirmação antes de
  qualquer execução real.
