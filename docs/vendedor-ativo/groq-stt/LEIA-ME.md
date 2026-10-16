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
