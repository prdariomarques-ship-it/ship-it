# voice-service — geração de voz autorizada (hospedagem própria)

Serviço **separado** do backend do Dario OS. Recebe um texto curto, gera fala em português do Brasil com a voz de um **perfil autorizado** e devolve **OGG/Opus mono 48 kHz** (formato de mensagem de voz do WhatsApp). Não envia nada a ninguém: quem envia é o backend, pela fila e pelo Evolution.

> Estado: serviço, limites, fila, armazenamento, formato e ferramentas de referência **testados** (54 testes, motor de teste). Os motores reais (Chatterbox/Qwen3-TTS) estão **escritos mas nunca carregaram pesos** — ver `docs/vendedor-ativo/MODELO_DE_VOZ.md`. Sem medições de modelo real.

## API (interna; token obrigatório, exceto `/healthz`)
| Rota | O que faz |
|---|---|
| `POST /v1/synthesize` `{request_id, text, language:"pt"}` | gera e guarda o áudio; mesma `request_id` = mesmo áudio (idempotente). Erros: 400 entrada, 401, 404 perfil, 413 texto longo, 422 áudio curto/longo, 429 fila cheia, 502 formato inválido, 503 motor não pronto, 504 timeout |
| `GET /v1/audio/{id}` | baixa (só o agente dono); `X-Audio-SHA256` |
| `DELETE /v1/audio/{id}` | apaga |
| `GET /readyz` | estado do motor/revisão/perfis do **próprio** agente |
| `GET /healthz` | vivo (sem detalhes) |

Segurança: `VOICE_TOKENS="loja=<32+ chars>"` — o nome é o **agente** e só ele usa o perfil de mesmo nome (o token do Twin nunca alcança a voz da loja). Escuta em `127.0.0.1` por padrão; no contêiner só em rede interna (`docker-compose.example.yml`, sem `ports:`). Sem `/docs`. Comparação de token em tempo constante. Corpo ≤ 8 KiB. Texto ≤ `VOICE_MAX_TEXT_CHARS` (350). Áudio ≤ 40 s. Concorrência `VOICE_MAX_CONCURRENCY` (1) + fila `VOICE_QUEUE_MAX` (4); excedeu = 429. Timeout de geração 180 s (a vaga só é liberada quando o thread do motor termina). Áudios em `VOICE_STORAGE_DIR` (0700/0600), TTL 900 s, apagados na subida.

## Perfil de voz (um por agente) — consentimento obrigatório
`profiles/<agente>/profile.json` + `reference.wav`. O serviço **recusa** perfil sem `consent.authorized=true`, titular e finalidade, ou cujo SHA-256 não confira. A gravação original é **copiada intacta** para `profiles/<agente>/original/`; `reference.wav` é só um recorte (+ mono). **Sem filtros, sem normalização, sem redução de ruído.**
```bash
python -m scripts.analyze_reference "WhatsApp Ptt ....ogg"            # volume, ruído, clipping, zumbido, janela sugerida (somente leitura)
python -m scripts.prepare_reference "WhatsApp Ptt ....ogg" --profiles-dir ./profiles --agent loja --start 3 --end 15 \
       --voice-owner "NOME" --consent-scope "assistente de vendas da Loja Marquescolor, voz sintética identificada" --confirm-authorized
```
`profiles/` é ignorado pelo git (só `profile.example.json`). A gravação **não deve ser enviada a serviços externos**.

## Executar
```bash
pip install -r requirements-chatterbox.txt        # ou requirements-qwen3tts.txt  (versões fixadas; instalação não exercitada aqui)
# pesos baixados FORA do serviço, com revisão fixada; o serviço roda offline (HF_HUB_OFFLINE=1)
VOICE_TOKENS="loja=$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" VOICE_ENGINE=chatterbox VOICE_MODEL_REVISION=<commit> \
  python -m uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8765
VOICE_TOKEN=... python -m scripts.make_samples --out /caminho/privado      # 3 amostras fictícias (atendimento, retomada, pós-venda)
python -m scripts.measure --agent loja --repeat 3 --out medicao.json        # tempo, RTF, pico de RAM/VRAM, concorrência (+ descrição do hardware)
```
Testes: `pip install -r requirements-dev.txt && pytest`.

## Limitações conhecidas
Sem modelo real testado aqui; o `Dockerfile` não foi construído (sem Docker no ambiente) e a imagem base precisa ter o digest fixado; a licença dos **pesos** precisa ser conferida nos cartões oficiais antes do uso; o PerTh (Chatterbox) marca o áudio; a reprodução como mensagem de voz depende da versão do Evolution e deve ser conferida no aparelho.


## Painel (`/panel`)

Interface web do **mesmo** serviço: usa o mesmo motor, a mesma fila (`/v1/synthesize`), os mesmos perfis e a mesma configuração (`VOICE_*`). Não cria motor, fila nem configuração paralelos e **não envia nada por WhatsApp**.

- Abrir `http://<host>:<porta>/panel` (por padrão só em `127.0.0.1`; acesso remoto, só por rede interna/VPN). As páginas estáticas não contêm dado algum; o token do agente é digitado no navegador, fica só em memória da aba e vale para `/v1/*`.
- Mostra: modo (**simulado** ou **real**), motor/modelo/revisão, perfil (consentimento, prefixo do hash da referência), checklist de pré-requisitos da voz real, fila (em geração, admitidos, áudios guardados), últimos pedidos (**só metadados**: id, resultado, tempo, nº de caracteres) e permite gerar um áudio de teste e ouvi-lo.
- `GET /v1/panel/status` (token obrigatório) alimenta a página; cada agente vê só o próprio perfil e o próprio histórico.

**O que este painel prova e o que não prova.** Testado com o motor **simulado** (`fake`): prova painel, fila compartilhada, rótulos e formato OGG/Opus. **Não prova áudio real com a voz do titular**: isso depende da gravação de referência, dos pesos do modelo e da validação (escuta) na máquina escolhida. Com o motor simulado o painel e o áudio são rotulados "não é a sua voz" e `real_voice_possible` é sempre `false`.

Teste em navegador real: `node scripts/e2e_painel.cjs captura.png` (ver variáveis no cabeçalho do script).
