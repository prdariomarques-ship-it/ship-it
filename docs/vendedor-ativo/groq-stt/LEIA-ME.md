# Transcrição de áudio com Groq (Whisper) — estado e como ligar

**Estado:** implementado no repositório (branch `feat/vendedor-ativo-voz`), **não aplicado na VPS**. Nada muda em produção até a chave ser criada e o patch ser aplicado com autorização.

## O que existe
- `backend/providers/stt/groq.py`: `GroqSTTProvider` (API compatível com a OpenAI, `/audio/transcriptions`). Modelo padrão `whisper-large-v3-turbo`, idioma `pt`, temperatura 0, 2 tentativas (429/5xx/rede), limite de 25 MB, sem chave = desabilitado. Falha, resposta vazia ou "alucinação" do Whisper (ex.: "Legendas pela comunidade Amara.org") levantam `STTProviderError`: nunca vira texto inventado. A chave não aparece em erros nem logs.
- `providers/stt/factory.py`: registra `groq` (continua `None` quando `STT_PROVIDER` está vazio).
- `utils/config.py`: `GROQ_API_KEY`, `GROQ_BASE_URL`, `GROQ_STT_MODEL`, `GROQ_STT_LANGUAGE`, `GROQ_STT_TIMEOUT_SECONDS`, `STT_INSTANCES`.
- `webhooks/router.py`: se `STT_INSTANCES` (lista separada por vírgula) não estiver vazia, o áudio de qualquer instância fora da lista **não é baixado nem enviado**.

## Para ligar (todos por variável de ambiente do contêiner; nunca no chat)
```
STT_PROVIDER=groq
GROQ_API_KEY=<chave nova, criada só para o Dario OS>
STT_INSTANCES=MARQUESCOLOR,b2b-sales
```
`STT_INSTANCES` deixa a instância do Twin (família, igreja) e a Azusa **de fora**: o áudio dessas conversas não sai do servidor. Para incluir a sua própria instância (áudios do dono), acrescente o nome dela, mas isso é decisão sua.

## Antes de aplicar (pendências suas)
1. Revogar a chave Groq que apareceu numa transcrição (X01) e criar uma **chave exclusiva** para o Dario OS (no print de 16/10 há chaves por uso: Aplicativo Android, Hermes, PC Windows, TypeWhisper; não reutilize nenhuma).
2. Conferir na VPS se já existe STT em produção (comando só de leitura enviado na conversa). Os arquivos de produção (`config.py`, `webhooks/router.py`, `factory.py`) podem ter patches que o repositório não tem: o script de aplicação só será gerado depois de comparar os hashes deles com a base.
3. Avisar clientes no aviso de privacidade que áudios podem ser transcritos por serviço externo (LGPD).

## Testes
`tests/test_groq_stt.py` (14, transporte HTTP simulado — **não** prova qualidade nem fala com a Groq) e 2 testes novos em `tests/test_audio_media_contract.py` (lista de instâncias). Mutações verificadas: sem a lista, sem o filtro de alucinação e sem o limite de tamanho, cada uma derruba testes. Suíte completa do backend (sem `test_gcalendar_tools.py`, que já falha na coleta sem as minhas mudanças): 23 falhas, todas também presentes sem a mudança (orquestrador/registros/estilo), nenhuma nova.

## Aplicação na VPS (pronta; só rodar com autorização)
Arquivos: `aplicar_groq.py` (edições ancoradas em config.py/factory.py/router.py do container), `aplicar_na_vps_groq.sh`, `rollback_groq.sh`, `groq.py`, e `BLOCO_COLAR_NA_VPS.txt` (cria tudo em `~/groq_stt` e confere o hash de cada arquivo).
1. Cole o bloco na VPS, depois: `cd ~/groq_stt && bash aplicar_na_vps_groq.sh`. A chave é pedida com digitação oculta.
2. O script lê os 3 arquivos do container, aplica as edições, confere cada cópia DENTRO do container, troca, grava `STT_PROVIDER`, `STT_INSTANCES` e `GROQ_API_KEY` no `/app/.env` (permissão 600), **reinicia o backend** e roda uma verificação funcional com 1 s de silêncio na Groq. Qualquer falha devolve os arquivos e o `.env` e reinicia de novo.
3. Desfazer: `bash rollback_groq.sh`.
- Recusa sem tocar em nada se: uma âncora não aparece exatamente 1 vez (o arquivo de produção difere do esperado), o Groq já foi aplicado, o `.env` já define essas chaves, o container não está healthy ou a chave não começa com `gsk_`.
- Instâncias liberadas por padrão: `MARQUESCOLOR,b2b-sales` (mude com `STT_INSTANCES_ALVO=... bash aplicar_na_vps_groq.sh`).
- `harness_groq.sh` testa a LÓGICA (18 casos, docker de mentira, usando os arquivos reais do commit anterior). **Não** prova o comportamento do Docker real nem da Groq real: a primeira execução real é o teste, e ela se desfaz sozinha se falhar.
- Limite conhecido: o `.env` dentro do contêiner e os arquivos copiados se perdem se o contêiner for recriado (mesma limitação G03 das outras mudanças).
