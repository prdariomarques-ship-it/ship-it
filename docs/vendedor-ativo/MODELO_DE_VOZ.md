# Gerador de voz — escolha, licença e estado dos testes

Data: 2026-10-12. Requisitos: português do Brasil, clonagem a partir de referência, código **e pesos** com licença compatível com uso comercial, execução própria, requisitos de hardware documentados. Sem ElevenLabs, sem extrair nada de serviço fechado.

## 1. Opções comparadas (fontes oficiais consultadas hoje)

| | **Chatterbox Multilingual** (Resemble AI) | **Qwen3-TTS Base** 0,6B / 1,7B (Qwen) | F5-TTS | XTTS-v2 (Coqui) |
|---|---|---|---|---|
| Código | **MIT** ([GitHub](https://github.com/resemble-ai/chatterbox); metadados do pacote `chatterbox-tts 0.1.7`: *License: MIT*) | **Apache-2.0** ([GitHub](https://github.com/QwenLM/Qwen3-TTS); `qwen-tts 0.1.1`: *Apache-2.0*) | MIT | MPL-2.0 ([GitHub](https://github.com/coqui-ai/TTS)) |
| Pesos | MIT segundo o cabeçalho do cartão do modelo (reportado por buscas; **não consegui abrir o Hugging Face daqui**) | Apache-2.0 segundo o cartão (idem; a página do GitHub **não** declara licença própria dos pesos) | **CC-BY-NC** ([GitHub](https://github.com/SWivid/F5-TTS): "licensed under the CC-BY-NC license due to the training data Emilia") → **não comercial** | licença do modelo não confirmada em fonte acessível aqui (a minha lembrança é restrição comercial) |
| Português | Sim (`language_id="pt"`; há ainda pacote de língua única pt-BR) | Sim (10 idiomas, incluindo português) | Não listado | não confirmado |
| Clonagem | Áudio de referência (~10 s no exemplo oficial); **sem transcrição** | Áudio + **transcrição exata** da referência (modo ICL); modo só-vetor sem transcrição, com qualidade menor | sim | sim |
| Hardware documentado | `cuda`/`cpu`/`mps`; VRAM **não** documentada; variante Nano "~3× tempo real em 8 núcleos" (só inglês) | exemplos em `cuda:0` + `bfloat16`; **sem** requisito mínimo documentado; Python 3.12 recomendado | — | — |
| Dependências | `torch==2.6.0`, `transformers==5.2.0`, `numpy<2` etc. (fixadas no pacote) | `transformers==4.57.3`, `accelerate==1.12.0` | — | — |
| Marca d'água | **PerTh embutida em todo áudio** (transparência a favor do uso identificado) | não informada | — | — |

**Decisão:** o serviço tem **dois adaptadores** (Chatterbox Multilingual e Qwen3-TTS Base) atrás da mesma interface; **recomendação inicial: Chatterbox Multilingual** (MIT, português nativo, não exige transcrição da referência, CPU possível) e **Qwen3-TTS como alternativa a comparar por escuta**. F5-TTS é descartado por licença dos pesos; XTTS-v2 fica fora por não ter licença comercial confirmada. A escolha final **só vale depois da escuta das amostras pelo proprietário** — não há afirmação de fidelidade nem de equivalência com ElevenLabs.

Pendente de conferência humana antes de uso real (não consegui verificar daqui): o texto da licença **dos pesos** nos cartões do Hugging Face; a revisão (commit) exata dos pesos a fixar em `VOICE_MODEL_REVISION`.

## 2. O que foi (e o que não foi) testado

- **Testado de verdade (54 testes, 1 pulado):** o serviço (`voice-service/`): autenticação por agente, perfil por agente, limites, fila limitada com 429, timeout que **não libera a vaga enquanto o thread roda**, idempotência por `request_id`, armazenamento 0700/0600 com limpeza por TTL, OGG/Opus mono 48 kHz decodificado de verdade, recusa de áudio inválido/longo/NaN, ferramentas de análise/preparo da referência (sem filtros, original preservado).
  Mutação: de 7 mutantes do serviço, 5 foram mortos de primeira e os 2 sobreviventes ganharam testes que os matam.
- **NÃO testado com modelo real:** `chatterbox_engine.py` e `qwen3_engine.py` foram escritos contra a API **lida no código dos pacotes publicados** (`chatterbox-tts 0.1.7`, `qwen-tts 0.1.1`), mas **nunca carregaram pesos**: o ambiente de desenvolvimento não alcança `huggingface.co` nem `modelscope.cn` (política de rede do ambiente; **não contornei**). Consequência: **sem amostras de voz reais e sem medição de tempo/RAM/VRAM de modelo real.** O motor `fake` (sinal de teste, recusado sem flag explícita) existe só para exercitar fila e formato — **não foi usado para gerar as amostras que o proprietário ouviria**.
- **Hardware deste ambiente (medição do ambiente, não do modelo):** 4 vCPU x86_64, 15 GiB de RAM, sem GPU. **VPS:** nenhum acesso nesta etapa; o `SESSION_TRACKING.md` registra ~268 MB de RAM livre e swap a 95% (informação do proprietário, 10/10) — **incompatível com hospedar o gerador**. O serviço foi feito para rodar em **outra máquina** (rede interna/VPN até o backend), mantendo Evolution e backend como estão.

## 3. Para desbloquear a medição e as três amostras

Uma das duas coisas (ou ambas):
1. Liberar no *Network access* do ambiente os hosts `huggingface.co` e seus CDNs (ou colocar os pesos já baixados, com a revisão fixada, em um volume que eu enxergue); **e** enviar a gravação `WhatsApp Ptt 2026-10-12 at 13.39.29.ogg` (não está neste ambiente; busquei em todo o disco e nos uploads).
2. Ou rodar na sua máquina/GPU: `scripts/analyze_reference.py` → `scripts/prepare_reference.py` → subir o serviço → `scripts/make_samples.py` (gera os 3 áudios fictícios) e `scripts/measure.py` (tempo, RTF, pico de RAM/VRAM, concorrência) — a gravação **não sai da sua máquina**.
