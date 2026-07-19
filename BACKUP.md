# Backup — Dario OS

## O que existe hoje

`scripts/backup.sh` cobre **PostgreSQL e Qdrant**:

- **PostgreSQL**: `pg_dump` plano, comprimido com `gzip`.
- **Qdrant**: um snapshot por coleção (descoberta dinamicamente via `GET /collections`, não hardcoded), via a própria API de snapshot do Qdrant — consistente num ponto no tempo, sem precisar parar o container. O snapshot é criado dentro do volume do Qdrant, copiado para fora com `docker cp` (o Qdrant não publica sua porta pro host, e sua imagem não tem `curl`/`wget` — as chamadas HTTP à API do Qdrant passam pelo container do `backend`, que já está na mesma rede) e apagado de dentro do container logo em seguida, pra não acumular snapshot sobre snapshot no próprio volume.
- Destino padrão: `$HOME/darioos-backups` (configurável via `BACKUP_DIR`).
- Retenção: mantém os 14 mais recentes de cada tipo (configurável via `RETENTION`), aplicada por coleção no caso do Qdrant.
- **Agendamento: automático.** `scripts/install-backup-timer.sh` instala e ativa um `systemd --user` timer (`docker/systemd/darioos-backup.{service,timer}`) rodando todo dia às 03:00 (com `Persistent=true` — se a máquina estiver desligada/suspensa nesse horário, roda assim que ligar de novo). Confirme que está ativo com `systemctl --user list-timers darioos-backup.timer`.
- **Pré-requisito no WSL, fora do escopo do script de instalação**: `systemd --user` só continua rodando sem depender de um terminal aberto se o *lingering* estiver habilitado para o usuário — sem isso, o timer é derrubado pouco depois do último shell fechar e só volta no próximo login. Rode uma vez (exige senha, por isso não é automatizado): `sudo loginctl enable-linger $USER`. Confirme com `loginctl show-user $USER` (`Linger=yes`) e `systemctl status user@$(id -u).service` (`Active: active`).

## O que NÃO é coberto pelo backup automático (decisão, não lacuna)

| Volume | Conteúdo | Por que não é coberto |
| --- | --- | --- |
| `redis_data` | Cache e janelas de rate limit | Puramente efêmero por design — `cache_service` já degrada para um fallback em memória quando o Redis está fora do ar (ver `docs/architecture.md`). Nada durável vive ali. |
| `openwa_data` | Perfil do Chromium usado pela sessão do WhatsApp | O próprio diretório é prefixado `_IGNORE_session` pela biblioteca (confirmado dentro do container em execução) — ela mesma sinaliza que é cache/perfil descartável. Não há mecanismo de exportação de sessão configurado neste deployment. Perdê-lo significa re-parear o WhatsApp (escanear o QR de novo), não perder dado — as mensagens já estão no Postgres. |
| `n8n_data` | Workflows configurados no n8n | Sem automação real configurada lá neste ambiente até agora (o Cognitive Pipeline nativo não depende do n8n). Se isso mudar, adicionar ao `backup.sh` é direto — mesmo padrão de `docker cp` de um volume. |
| `caddy_data` / `caddy_config` | Certificados TLS | Recuperável automaticamente (Caddy reemite na próxima subida). |

## Verificação de backup (watchdog automático)

Ter um timer agendado não é o mesmo que saber que o backup realmente rodou e produziu arquivos usáveis — o próprio `darioos-backup.timer` já ficou meses sem rodar de fato nesta máquina (por falta de lingering, ver acima) sem que isso aparecesse em lugar nenhum. Por isso existe um segundo watchdog, independente, dedicado só a checar o backup:

### Arquitetura

- **`scripts/verify-backup.sh`** — script somente-leitura (nunca modifica backup, banco ou unidade systemd). Roda todos os checks abaixo e escreve um relatório com timestamp em `$BACKUP_DIR/verify-reports/verify-<AAAAMMDD-HHMMSS>.log`. Idempotente: pode ser rodado manualmente quantas vezes quiser, cada execução só gera seu próprio relatório, nada é sobrescrito ou mutado.
- **`docker/systemd/darioos-backup-verify.{service,timer}`** — `oneshot` + timer diário, instalados junto com os do backup por `scripts/install-backup-timer.sh` (mesmo `systemd --user`, mesma dependência de lingering documentada acima). Como o script é só leitura e idempotente, o serviço tem `Restart=on-failure` (até 3 tentativas por hora, `RestartSec=300`) e `TimeoutStartSec=300` — uma falha transitória (ex.: D-Bus ocupado logo após o boot) não precisa esperar até o próximo dia pra ser reavaliada.

### Agenda

`darioos-backup.timer` roda às **03:00**; `darioos-backup-verify.timer` roda às **03:15** (`OnCalendar=*-*-* 03:15:00`, `Persistent=true`), 15 minutos depois — tempo de sobra para o backup (Postgres + Qdrant) terminar antes da checagem começar.

### O que é verificado

Cada item vira sua própria linha `[PASS]`/`[FAIL]` no relatório:

1. `darioos-backup.timer` disparou hoje (`LastTriggerUSec`).
2. `darioos-backup.service` terminou com sucesso (`Result=success`, `ExecMainStatus=0`).
3. Nenhuma das duas unidades está em estado `failed` persistente — checagem restrita a essas duas unidades (esta máquina também roda `spcx-monitor`, `signal-engine` e `renda-fixa-monitor` no mesmo `systemd --user`; uma falha desses não deve aparecer aqui como se fosse do backup).
4. Nenhuma entrada de prioridade `err` ou pior no journal de `darioos-backup.service` de hoje.
5. Os arquivos esperados existem (≥1 dump do Postgres, ≥1 snapshot do Qdrant) e são de hoje.
6. Nenhum arquivo com tamanho 0.
7. Integridade: `gunzip -t` no(s) dump(s) do Postgres (falha aqui é `[FAIL]`); `tar -tf` nos snapshots do Qdrant — best-effort: se falhar, vira `[WARN]` em vez de `[FAIL]`, porque o formato exato do snapshot do Qdrant não é garantido como tar puro em toda versão, e tamanho > 0 já foi confirmado no item 6.

O relatório também traz tamanho total dos arquivos do dia, horário de início/fim e duração da execução do backup, e o trecho relevante do `journalctl` para debug direto, sem precisar rodar mais nada manualmente.

### Notificação (opcional)

Por padrão, o watchdog só escreve o relatório em disco — nada é enviado a lugar nenhum. Se `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` estiverem definidos (via um `.env` na raiz do projeto, carregado pela unidade systemd através de `EnvironmentFile=-%h/projects/dario-os/.env`), uma falha dispara um alerta automaticamente; um sucesso só notifica se `TELEGRAM_NOTIFY_ON_SUCCESS=true` também estiver definido, pra não gerar ruído diário. Este projeto **não** reaproveita o bot Telegram de `work/send_fx_telegram.py` — aquele pertence a um projeto pessoal separado (raiz e `.env` diferentes); se quiser notificação aqui, configure um bot/token próprios para o Dario OS.

### Procedimento de recuperação, se o relatório vier `[FAIL]`

1. Leia o relatório mais recente em `$BACKUP_DIR/verify-reports/` — cada `[FAIL]` já indica a causa provável, e o trecho de `journalctl` no final do arquivo tem o log real da execução.
2. Causas mais comuns, na ordem em que já apareceram nesta máquina:
   - **Timer não disparou** → cheque `loginctl show-user $USER` (`Linger=yes`?) e `systemctl status user@$(id -u).service` (`Active: active`?) — é o mesmo pré-requisito de lingering acima, e é a causa raiz que já aconteceu de verdade nesta máquina.
   - **Serviço falhou** → `journalctl --user -u darioos-backup.service -n 100` para ver o erro exato (ex.: `docker compose` fora do ar, Postgres/Qdrant não respondendo).
   - **Arquivo corrompido/vazio** → rode `scripts/backup.sh` manualmente e observe a saída diretamente, sem esperar o timer.
3. Depois de corrigir a causa raiz, rode `scripts/backup.sh` manualmente e, em seguida, `scripts/verify-backup.sh` manualmente para confirmar que voltou a `PASS` antes de esperar o próximo ciclo automático.

### Testes automatizados

`scripts/tests/test_verify_backup.sh` roda o script real (não uma reimplementação) contra 7 cenários — tudo saudável, timer não disparou, serviço falhou, arquivos ausentes, dump corrompido, erros no journal, unidade em estado `failed` — com `systemctl`/`journalctl` substituídos por fakes via `PATH`, então não precisa de um ambiente systemd real para rodar. Execute com `bash scripts/tests/test_verify_backup.sh`.

## Restauração

Ver `RESTORE.md` — `scripts/restore.sh` automatiza a restauração de ambos (Postgres e Qdrant), com confirmação obrigatória antes de sobrescrever dados atuais.
