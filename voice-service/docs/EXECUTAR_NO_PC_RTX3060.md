# Voz real no PC do titular (Windows, RTX 3060 12 GB) — passo a passo

Faz o `voice-service` gerar áudio **real** com a sua voz autorizada. A gravação **não sai do PC**. O que estas etapas provam: motor
real carregado, qualidade, tempo e uso de memória **nesta máquina**. Não provam o envio pelo WhatsApp (isso é o passo 7).
Pesquisa que sustenta o roteiro: ver `docs/vendedor-ativo/MODELO_DE_VOZ.md` (seção "Confirmado em fontes oficiais").

Comandos em **PowerShell**. Não cole tokens no chat: gere-os localmente e guarde em lugar seguro.

## 0. Pré-requisitos
- Windows 10/11, driver NVIDIA atual (`nvidia-smi` funciona), ~15 GB livres em disco.
- Python **3.11** (64 bits) e Git. Se o `python --version` não mostrar 3.11, instale em python.org.

## 1. Código e ambiente
```powershell
git clone https://github.com/prdariomarques-ship-it/ship-it.git; cd ship-it; git checkout feat/vendedor-ativo-voz
cd voice-service
py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1
# PyTorch com CUDA ANTES do chatterbox (ele fixa torch==2.6.0):
pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
pip install -r requirements-chatterbox.txt
pip install --no-deps chatterbox-tts==0.1.7   # SEM dependências: o pacote declara gradio==6.8.0, que conflita com o starlette do serviço (o código não usa gradio)
python -c "import torch;print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"   # precisa mostrar True e a RTX 3060
```

## 2. Pesos (precisa de internet com acesso a huggingface.co) + revisão fixada
```powershell
pip install huggingface_hub
python scripts\download_weights.py --dest C:\models\chatterbox
# no fim ele IMPRIME: VOICE_MODEL_REVISION=<commit>  -> anote
```
Antes de usar para fins comerciais, **leia a licença no cartão do modelo** (https://huggingface.co/ResembleAI/chatterbox): o cartão
declara MIT; a conferência do texto é sua/da equipe (eu não consegui abrir o Hugging Face do ambiente de desenvolvimento).

## 3. Perfil de voz a partir da SUA gravação (consentimento explícito)
```powershell
$ref = "C:\caminho\WhatsApp Ptt 2026-10-12 at 13.39.29.ogg"
python -m scripts.analyze_reference $ref                     # só lê; sugere o melhor trecho (use ~10–15 s limpos)
python -m scripts.prepare_reference $ref --profiles-dir C:\voz\profiles --agent loja --start 3.0 --end 15.0 `
  --voice-owner "Dário Marques Neto" --consent-scope "voz sintética do assistente da Loja Marquescolor, uso autorizado pelo titular" --confirm-authorized
```
Ajuste `--start/--end` ao trecho sugerido. O original fica intacto em `original/` com SHA-256. **Nenhum filtro é aplicado.**

## 4. Subir o serviço (só na própria máquina)
```powershell
$env:VOICE_TOKENS = "loja=" + (python -c "import secrets;print(secrets.token_urlsafe(32))")   # token do agente 'loja'; guarde
$env:VOICE_ENGINE = "chatterbox"; $env:VOICE_DEVICE = "cuda"
$env:VOICE_MODEL_DIR = "C:\models\chatterbox"; $env:VOICE_MODEL_REVISION = "<o commit impresso no passo 2>"
$env:VOICE_PROFILES_DIR = "C:\voz\profiles"; $env:VOICE_STORAGE_DIR = "C:\voz\tmp"; $env:HF_HUB_OFFLINE = "1"
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765
```
Abra `http://127.0.0.1:8765/panel`, informe o token e confira: **modo "real"**, pesos carregados, perfil com consentimento. Se aparecer
"MOTOR SIMULADO", o `VOICE_ENGINE` está errado.

## 5. Três amostras e medição (resultados para você e para mim)
Em outro PowerShell, com o mesmo ambiente ativo:
```powershell
$env:VOICE_URL = "http://127.0.0.1:8765"; $env:VOICE_TOKEN = "<o token do passo 4>"
python -m scripts.make_samples --out C:\voz\amostras          # 3 áudios fictícios: OUÇA antes de aprovar
python -m scripts.measure --agent loja --repeat 3 > C:\voz\medicao.json
```
Envie-me só `medicao.json` (sem áudio, sem token). **A aprovação da voz é sua**, por escuta; nada é ligado antes disso.

## 6. Acesso a partir da VPS (sem abrir porta pública)
O backend (VPS) precisa chamar o serviço do PC. Use uma rede privada (ex.: Tailscale ou WireGuard) e faça o serviço escutar **só**
no IP privado do PC (`--host <ip privado>`), nunca em `0.0.0.0` exposto. Na VPS: `STORE_VOICE_URL=http://<ip privado>:8765`,
`STORE_VOICE_TOKEN=<token>` (arquivo de ambiente, nunca no chat). Mantenha `STORE_VOICE_ENABLED=false` até passar pelo passo 7.

## 7. Transporte Evolution e aparelho (antes de qualquer cliente)
Com um contato **seu** (preferência `reply_mode=audio`) e `STORE_VOICE_ENABLED=true` só no ambiente de teste: confira no celular que
chega como **nota de voz** (ícone de microfone, "gravando áudio…"), com o texto escrito antes. Se não tocar como nota de voz, teste
`EVOLUTION_VOICE_ENCODING=false` (bytes como estão) ou `true` (o Evolution converte com ffmpeg) e me diga o resultado.

## Pacote pt-BR oficial (Space da Resemble) em ambiente separado

O `chatterbox-tts 0.1.7` do PyPI só carrega o modelo V2 (idioma `pt`, com sotaque) e tem um detector de repetição que, com a sua referência,
encerrou a fala depois de 0,5–1,5 s (`forcing EOS token, token_repetition=True`). O código do Space pt-BR não tem esse detector e carrega
`t3_pt_br.safetensors` + `s3gen_v3.pt`. Ele pede outras versões (torch 2.8/cu128, transformers 4.46.3), por isso vai num ambiente à parte (`.venv-ptbr`);
o `.venv` atual continua como reserva.

```powershell
cd C:\Users\dario\FlowCore\ship-it\voice-service
python -m venv .venv-ptbr
.\.venv-ptbr\Scripts\python.exe -m pip install --upgrade pip
.\.venv-ptbr\Scripts\python.exe -m pip install huggingface_hub
# código do Space (sem áudios/imagens) em C:\voz\space_ptbr
.\.venv-ptbr\Scripts\python.exe -c "from huggingface_hub import snapshot_download as s; print(s('ResembleAI/Chatterbox-Multilingual-TTS-pt-br', repo_type='space', local_dir=r'C:\voz\space_ptbr', ignore_patterns=['*.wav','*.mp3','*.png','*.jpg']))"
Get-Content C:\voz\space_ptbr\requirements.txt
.\.venv-ptbr\Scripts\python.exe -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv-ptbr\Scripts\python.exe -m pip install -r C:\voz\space_ptbr\requirements.txt
.\.venv-ptbr\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
.\.venv-ptbr\Scripts\python.exe -m scripts.compare_variants --space-dir C:\voz\space_ptbr --reference "<gravacao.wav>" --start 7 --end 19 --variant "cfg=0.5,exg=0.5" --variant "cfg=0.3,exg=0.5,temp=0.7" --variant "cfg=0,exg=0.5" --out C:\voz\teste_ptbr
```

### Geração caiu ou saiu áudio cortado: refazer só o que falta
Rode o MESMO comando acrescentando `--retomar`. Ele reaproveita as letras do `chave.json`, confere cada `.wav` já gerado (duração compatível com o texto: frase curta demais = cortada, longa demais = não parou de falar) e gera de novo **só** o que não existe ou saiu incompleto. Se tudo estiver completo, nem carrega o modelo. Ao final lista o que ainda estiver incompleto e sai com código 1. Cada geração nova imprime `ATENÇÃO: ...` quando já sai suspeita.

## Motor `chatterbox_ptbr` no serviço (configuração aprovada na escuta às cegas de 17/10/2026)

Variante **C**: `cfg_weight=0.3`, `exaggeration=0.7`, `temperature=0.8`. Aprovada só em duas das três frases (a 1ª, de atendimento inicial, não
passou): é "razoável", não "excelente" — a escuta no aparelho (passo 7) ainda decide. O ritmo veio da **referência compacta** (pausas > 0,3 s
reduzidas para 0,2 s; silêncio de 58% para 26%): sem isso todas as variantes saíram em "slow motion", porque o Chatterbox copia o ritmo da gravação.

```powershell
cd C:\Users\dario\FlowCore\ship-it\voice-service
# 1) referência compacta (não toca no original). Se já existe C:\voz\ref_compacta.wav, aprovada por escuta, USE ESSE arquivo.
.\.venv-ptbr\Scripts\python.exe -m scripts.compact_pauses "<gravacao_original.wav>" C:\voz\ref_compacta.wav
# 2) pesos pt-BR em pasta fixa + revisão (precisa de internet uma vez; depois o serviço roda offline)
.\.venv-ptbr\Scripts\python.exe -m scripts.download_ptbr_weights --space-dir C:\voz\space_ptbr --dest C:\models\chatterbox_ptbr
# 3) perfil de voz a partir da referência compacta (consentimento explícito, como no passo 3)
.\.venv-ptbr\Scripts\python.exe -m scripts.prepare_reference C:\voz\ref_compacta.wav --profiles-dir C:\voz\profiles --agent loja `
  --voice-owner "Dário Marques Neto" --consent-scope "voz sintética do assistente da Loja Marquescolor, uso autorizado pelo titular" --confirm-authorized
# 4) serviço no ambiente do pacote pt-BR (as dependências do serviço — requirements.txt — precisam estar nesse ambiente)
.\.venv-ptbr\Scripts\python.exe -m pip install -r requirements.txt
$env:VOICE_ENGINE = "chatterbox_ptbr"; $env:VOICE_DEVICE = "cuda"
$env:VOICE_PTBR_SPACE_DIR = "C:\voz\space_ptbr"; $env:VOICE_MODEL_DIR = "C:\models\chatterbox_ptbr"
$env:VOICE_MODEL_REVISION = "<o valor impresso no passo 2>"
$env:VOICE_CHATTERBOX_CFG_WEIGHT = "0.3"; $env:VOICE_CHATTERBOX_EXAGGERATION = "0.7"; $env:VOICE_CHATTERBOX_TEMPERATURE = "0.8"
# demais variáveis (VOICE_TOKENS, VOICE_PROFILES_DIR, VOICE_STORAGE_DIR) como no passo 4
.\.venv-ptbr\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765
```

O motor recusa carregar se já houver outro pacote `chatterbox` na memória (o do PyPI) ou se `VOICE_MODEL_REVISION` estiver vazio ou passar de
64 caracteres (limite da coluna `store_voice_sends.model_revision`). `chatterbox_pt_br_pack` (config antiga) não é usado por nenhum motor.
Cobertura: duplo do pacote do Space (sem pesos reais); a validação real é a escuta.

**Disponibilidade:** o gerador roda na GPU do PC do titular. PC desligado ou fora da rede = o job `store.voice_reply` termina em
`failed_before_send`; o cliente já recebeu a resposta por escrito, então só o áudio é perdido. A VPS não hospeda o gerador (RAM e swap
insuficientes, sem GPU).
