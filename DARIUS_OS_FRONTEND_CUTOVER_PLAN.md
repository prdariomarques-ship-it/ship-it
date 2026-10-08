# Darius OS — Plano de troca e reversão SOMENTE do frontend

Escopo: troca da imagem do serviço `frontend` no `darioos-evolution`, com um
procedimento de reversão descrito e uma imagem de reversão retida
localmente antes do corte — não uma garantia de que a reversão sempre
funciona em qualquer cenário (ela ainda depende dos 3 pontos pendentes na
seção 2, principalmente de como `image`/`build`/`depends_on` estão
definidos de verdade no arquivo real). Não toca backend, WhatsApp, banco ou
qualquer outro serviço. Não usa o Compose genérico do repositório
(`docker/docker-compose.yml`, projeto `darioos`) como fonte de verdade —
serve só de referência estrutural, citada explicitamente onde usada. A
fonte de verdade é a configuração real confirmada na VPS em 08/10/2026,
abaixo — mas as informações da seção 1 vieram de uma descrição verbal dos
campos observados (inspeção/estado do container), não da leitura direta do
arquivo `app.compose.prepared.json` por mim; onde isso importa (campos que
podem ser declaração explícita OU comportamento padrão do Compose), marco
isso explicitamente em vez de presumir.

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

**Duas ressalvas sobre este fragmento, antes de usá-lo:**

- `container_name: darioos-evolution-frontend-1` abaixo é o que a inspeção
  do container mostrou, mas esse nome também é exatamente o padrão que o
  Compose gera por si só (`<projeto>-<serviço>-<índice>`) quando **não** há
  um `container_name:` explícito no arquivo. Não tenho como saber, só pela
  inspeção, se o `app.compose.prepared.json` real declara esse campo
  explicitamente ou se é só o nome default do projeto `darioos-evolution` +
  serviço `frontend`. Preservar a declaração real do arquivo (ou a ausência
  dela) importa pra não introduzir um `container_name:` que não existia.
- `networks: darioos-evolution_darioos: external: true` é a minha melhor
  suposição de como referenciar essa rede partindo de um Compose isolado
  só do frontend, mas não confirmei se essa rede é de fato `external` no
  arquivo real ou se é definida ali mesmo (`darioos-evolution` é o nome do
  projeto, e Compose prefixa nomes de rede com o nome do projeto por
  padrão — `darioos-evolution_darioos` é consistente com uma rede chamada
  `darioos` definida *dentro* do próprio Compose, não necessariamente uma
  rede `external`). Qualquer um dos dois pode estar certo; o arquivo real
  decide.

```yaml
services:
  frontend:
    # PENDENTE (ver seção 2.1): image: <registro>/<repo>:<tag>  OU  build: {...}
    # PENDENTE (ver seção 2.1): pull_policy
    # NÃO CONFIRMADO — ver ressalva acima: pode ser este valor explícito,
    # ou pode ser omitido e deixado no default do Compose (mesmo resultado
    # observado). Preserve o que o arquivo real tiver.
    container_name: darioos-evolution-frontend-1
    restart: unless-stopped
    platform: linux/amd64
    networks:
      # NÃO CONFIRMADO — ver ressalva acima sobre external: true vs. rede
      # definida localmente no próprio arquivo.
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
  # NÃO CONFIRMADO se é "external: true" — ver ressalva acima.
  darioos-evolution_darioos:
    external: true
```

Nenhum volume declarado (confirmado: nenhum existe hoje). Nenhuma porta
publicada no host (confirmado: 3000/tcp só interna).

## 4. Imagem candidata final — preparada e preservada nesta sessão

**Origem:** commit `c0ff149` de `frontend/darius-os-visual-prod-base` —
Next.js 16.3.6, Sidebar/branding reconciliados com `master`, bug de foco
mobile→desktop corrigido, `.dockerignore` adicionado.

**Precisão sobre o build:** o arquivo `frontend/Dockerfile` commitado no
repositório não foi editado — isso é verdade. Mas a imagem NÃO foi
construída a partir dele diretamente: usei um arquivo irmão, descartável e
nunca commitado (`Dockerfile.sandboxtest`), cujo estágio `deps` É diferente
do `Dockerfile` real (ver próxima seção) — dizer que "o Dockerfile real foi
usado sem nenhuma alteração" seria impreciso, porque o comando de build
efetivamente executado (`docker build -f Dockerfile.sandboxtest ...`) não
usou o arquivo real, usou uma variante dele. O que É verificadamente
verdadeiro, e é a base de confiança deste candidato, é mais estreito:
**os estágios `builder` e `runner` dessa variante — os únicos cujas
instruções determinam o conteúdo da imagem final — são byte a byte
idênticos aos mesmos estágios do `Dockerfile` real**; só o estágio `deps`
(descartado no build multi-stage, seu conteúdo não é copiado pra nenhum
estágio seguinte) foi alterado, e só para confiar na CA deste sandbox.

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
commitada** do Dockerfile (`Dockerfile.sandboxtest`), que difere do
Dockerfile real **apenas no estágio `deps`** (adicionando
`NODE_EXTRA_CA_CERTS` apontando pra uma cópia temporária do bundle de CA do
sandbox, só para o `npm ci` conseguir baixar pacotes). Verifiquei por diff
que os estágios `builder` e `runner` dessa variante são **byte a byte
idênticos** aos mesmos estágios do `frontend/Dockerfile` real (`diff` entre
os dois a partir de `FROM node:20-alpine AS builder`: saída vazia, exit
code 0) — isso prova que as instruções que produzem o conteúdo da imagem
final são as do Dockerfile real, não que "o Dockerfile inteiro" é
idêntico (o estágio `deps` genuinamente difere, mesmo sendo descartado).

**Verificação de que nada do sandbox chega na imagem final — além do
`docker history`, que só mostra instruções de camada, não o filesystem
resultante nem a configuração efetiva:**

- `docker history --no-trunc` na imagem final: nenhuma camada do estágio
  `deps` aparece nela, e não há nenhuma referência a `sandbox`,
  `ca-bundle` ou `NODE_EXTRA_CA_CERTS` no histórico de camadas.
- `docker inspect --format '{{json .Config.Env}}'` na imagem final: só
  `PATH`, `NODE_VERSION`, `YARN_VERSION`, `NODE_ENV=production` — as
  variáveis padrão da imagem-base `node:20-alpine`. Nenhum
  `NODE_EXTRA_CA_CERTS`, nenhuma variável de proxy.
- Varredura do filesystem real de um container rodando a partir dessa
  imagem (`find / -xdev -iname "*sandbox*" -o -iname "*ca-bundle*" -o
  -iname "*.sandboxonly" -o -iname "*ccr*"`): o único resultado é
  `/app/node_modules/next/dist/server/web/sandbox/sandbox.js` — módulo
  interno do próprio Next.js, sem relação com este sandbox de execução.
  Nenhum arquivo de certificado ou configuração de confiança temporária
  encontrado.
- `/tmp` dentro do container final: vazio — confirma que o certificado
  temporário (colocado em `/tmp/sandbox-ca.crt` só no estágio `deps`,
  descartado) não está presente.
- `env` do processo em execução dentro do container: confirma as mesmas
  variáveis do `docker inspect`, nada adicional.
- O bundle de CAs públicas padrão do sistema, `/etc/ssl/certs/ca-certificates.crt`,
  está presente e com tamanho normal (217769 bytes) — não foi removido nem
  alterado em nenhuma etapa desta verificação.

Nenhum certificado, segredo ou configuração de confiança temporária deste
sandbox está presente na imagem final — confirmado por configuração e por
filesystem, não só pelo histórico de camadas. Os arquivos descartáveis
(`Dockerfile.sandboxtest`, a cópia da CA) foram apagados do disco do
projeto ao final; não foram commitados.

### Evidência de build e smoke test (contra a imagem candidata, porta de teste isolada)

```
npm run build dentro do container: 37 rotas, mesmo conjunto de sempre, sem erro de TypeScript/lint.

GET /                → 200, contém "Darius OS"
GET /login            → 200
GET /sw.js            → 200, content-type application/javascript
GET /admin/briefing    → 200 (shell protegido; guard roda no client)
GET /pessoal           → 200

Probe de healthcheck candidata — executada via `docker exec ... sh -c
'...'` (hostname resolvido pelo shell do container, não pelo shell de
quem roda o comando; ver a mesma ressalva na seção 5, passo 7):
  sh -c 'wget http://$(hostname):3000/'   → OK
  sh -c 'wget http://localhost:3000/'     → FALHOU (connection refused)
  (confirma o mesmo gotcha documentado no Compose genérico do repositório)
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

- Exportada via `docker save | gzip`: `darius-os-frontend-c0ff149.tar.gz`,
  72921639 bytes.
- SHA256 completo do arquivo original (64 hex, não abreviado):
  ```
  bf54023a6e64293a602162e761e90f504c80ef14ac0da344a718c2d1c00eeb6a
  ```
- Round-trip verificado nesta sessão: removi a imagem local, recarreguei só
  a partir do tarball (`docker load -i ...`) e o ID resultante bateu
  exatamente com o ID original acima. Testei `/` novamente após o reload: 200.
- O arquivo único (72921639 bytes) excede o limite de envio direto deste
  canal (30 MiB). Foi dividido binariamente em 4 partes de no máximo 20 MiB
  cada, sem recompressão, com nome, tamanho e SHA256 de cada parte no
  `MANIFEST.txt` entregue junto. Reconstruí as partes nesta mesma sessão
  (`cat part001..part004 > reconstructed.tar.gz`), confirmei hash idêntico
  ao original por `sha256sum` e por `cmp` byte a byte, e confirmei que
  `docker load` a partir do arquivo reconstruído produz o mesmo Image ID.
- **Status da entrega: pendente de confirmação.** As partes e o manifesto
  foram enviados nesta rodada; a imagem original e o tarball completo
  continuam preservados no disco desta sessão até que o recebimento e a
  integridade (hash final após reconstrução) sejam confirmados.

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
5. **Recriar só o frontend, sem build nem pull acidental.** `--no-deps`
   evita recriar outros serviços, mas não impede, por si só, que o Compose
   tente *buildar* (se o serviço real usa `build:`) ou *puxar* de um
   registro (se usa `image:` sem a imagem já carregada localmente) — e eu
   não sei qual dos dois é o caso real (ver seção 2.1). Fixe o projeto e o
   caminho do arquivo explicitamente, e force "nada de build, nada de
   pull" até confirmar qual dos dois cenários é real:
   ```
   cd /opt/chroma-migration-20260927
   docker compose -p darioos-evolution \
     -f /opt/chroma-migration-20260927/app.compose.prepared.json \
     up -d --no-deps --no-build --pull never frontend
   ```
   Se o serviço real usa `build:` em vez de `image:`, `--no-build` por si
   só não é suficiente para garantir que a imagem carregada via `docker
   load` seja a usada — nesse caso o campo `image`/`build` do arquivo
   precisa ser ajustado primeiro (passo 4) para referenciar a imagem já
   carregada, e não um contexto de build. **Não execute este passo
   enquanto a seção 2.1 não estiver confirmada** — o comando acima evita
   os piores acidentes (build ou pull indesejado), mas não substitui saber
   de verdade como o serviço está definido.
6. Acompanhar `docker compose -p darioos-evolution -f
   /opt/chroma-migration-20260927/app.compose.prepared.json ps frontend`
   até `healthy` (com os tempos da seção 1, até ~2 min).
7. Smoke test real a partir da rede interna (porta 3000 não é publicada).
   **Atenção:** `$(hostname)` precisa ser resolvido pelo shell *dentro* do
   container, não pelo shell do operador na VPS — se for escrito sem
   aspas simples envolvendo todo o comando interno, o `$(hostname)` é
   expandido PELO HOST antes de chegar ao `docker exec`, substituindo o
   hostname da VPS (errado) em vez do hostname do container:
   ```
   docker exec darioos-evolution-frontend-1 sh -c 'wget -qO- http://$(hostname):3000/login'
   ```
   As aspas simples em torno de todo o comando passado a `sh -c` são o que
   impede o shell do host de expandir `$(hostname)` antes da hora. Depois,
   uma vez confirmado o roteamento da seção 2.3, repetir o smoke pela URL
   pública (`/`, `/login`, `/api/...` continuando a bater no backend).

## 6. Reversão (frontend-only)

1. Repor o campo `image` do serviço `frontend` em
   `/opt/chroma-migration-20260927/app.compose.prepared.json` para
   `darius-os-frontend:rollback-20261008` (criada no passo 2 da seção 5)
   — ou, equivalentemente, para o ID original
   `sha256:23357543fb50fd2b4e7c94454f80c85e214093f1e9cee53b44fd11376098e84a`.
2. Mesma ressalva da seção 5 sobre build/pull acidental — fixar projeto e
   caminho, sem build nem pull:
   ```
   cd /opt/chroma-migration-20260927
   docker compose -p darioos-evolution \
     -f /opt/chroma-migration-20260927/app.compose.prepared.json \
     up -d --no-deps --no-build --pull never frontend
   ```
3. Confirmar `healthy` de novo pelos mesmos passos 6–7 da seção 5.
4. **O que a reversão cobre de fato, sem prometer mais do que isso**: o
   serviço não tem volumes segundo a informação confirmada na seção 1 (não
   verificada por mim diretamente no arquivo), então, se essa informação
   estiver correta, não há estado em disco do próprio container para
   recuperar — mas isso não é uma garantia geral de "sem risco de perda de
   dado": conexões em andamento no momento da troca são interrompidas, e
   qualquer estado do frontend que dependa de algo fora do container (ex.:
   sessões/cookies do lado do cliente) não é coberto por este
   procedimento. A reversão troca a imagem de volta e confirma saúde — não
   é uma reversão transacional de todo o sistema.

## 7. Declarado — não feito nesta entrega

- Nenhum comando das seções 5 e 6 foi executado contra a VPS; nenhum
  acesso à VPS foi feito nesta rodada.
- Backend, WhatsApp, banco e qualquer outro serviço não foram tocados.
- Os 3 pontos da seção 2 continuam pendentes de confirmação antes de
  qualquer execução real.
- A imagem candidata e o tarball original não foram apagados do disco
  desta sessão — ficam preservados até a confirmação de recebimento e
  integridade das partes entregues (`MANIFEST.txt`).
- As duas ressalvas da seção 3 (`container_name` e `networks.external`)
  continuam sem confirmação contra o arquivo real — o fragmento de Compose
  é um ponto de partida, não uma cópia verificada do que está lá.
