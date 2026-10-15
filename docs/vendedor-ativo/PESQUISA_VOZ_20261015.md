# Pesquisa de viabilidade — "ressuscitar" o gerador de voz (agente Celes) — 15/10/2026

Escopo: modelos abertos de síntese de voz com clonagem, português do Brasil, execução própria. Fontes na web; **Hugging Face e Reddit não foram acessíveis** (política de rede / bloqueio da ferramenta; não contornado). Nada abaixo foi testado com áudio real.

## Achados que mudam o que já estava escrito
1. **Chatterbox tem pacote oficial pt-BR** (Single Language Pack: pt-br, pt-pt, es-latam, es, zh, hi) além do multilíngue V3 (0,5B, 23+ línguas, MIT, marca d'água PerTh). Fonte: README do repositório resemble-ai/chatterbox. Nome do repositório de pesos citado por busca: `ResembleAI/Chatterbox-Multilingual-pt-br` (**não confirmado: HF inacessível**).
2. **Risco real com `language_id="pt"` no multilíngue**: issue #281 do Chatterbox (aberta, sem resposta de mantenedor) relata sotaque europeu mesmo com referência brasileira e erro em palavras com til (milhões, coração). O adaptador atual (`voice-service/app/engines/chatterbox_engine.py`) usa `ResembleAI/chatterbox` + `language_id="pt"`; **o pacote pt-BR deve ser avaliado antes de qualquer escolha**.
3. **Dica oficial anti-sotaque**: referência na MESMA língua do texto; `cfg_weight=0` reduz vazamento de sotaque da referência; padrões 0,5/0,5.
4. **Qwen3-TTS**: português suportado; Apache-2.0 no repositório (a página não declara licença própria dos pesos); clonagem exige áudio + transcrição (`x_vector_only_mode` dispensa, com qualidade menor); sem VRAM oficial (guias de terceiros: ~2–4 GB para 0,6B e ~6–8 GB para 1,7B; a RTX 3060 12 GB cabe, sem benchmark). Existe fine-tune acadêmico brasileiro (sotaque paraibano) `acidente/fala_pb_checkpoints` (Qwen3-TTS 1,7B Apache-2.0; F5-TTS e Fish Speech nesse repositório são CC-BY-NC) — sotaque regional, não neutro.

## Quadro de licenças (comercial)
| Modelo | pt-BR | Clona | Licença | Veredito |
|---|---|---|---|---|
| Chatterbox Multilingual V3 / pacote pt-br | sim (pacote dedicado) | sim (~10 s) | MIT (código; cartão dos pesos a conferir) | **candidato nº 1** |
| Qwen3-TTS Base 0,6B/1,7B | sim | sim (precisa transcrição) | Apache-2.0 (repo) | **candidato nº 2** |
| Kokoro 82M | sim (pf_dora, pm_alex, pm_santa) | não (vozes prontas) | Apache-2.0 | só para voz fixa/CPU; nota C em site de terceiros |
| Pocket TTS (Kyutai) | divergente entre fontes | sim | código MIT; vozes têm licença própria | verificar na fonte |
| CosyVoice 3 | não confirmado | sim | Apache-2.0 (terceiros) | verificar suporte a português |
| F5-TTS pt-br (firstpixel etc.) | sim | sim | CC-BY-NC | **descartado (não comercial)** |
| Fish Speech / Fish Audio S2 Pro | sim | sim | CC-BY-NC-SA / licença de pesquisa | **descartado** |
| Voxtral TTS (Mistral) | sim | pesos abertos limitados a vozes fixas (relato) | CC BY-NC 4.0 | **descartado** (comercial só via API paga) |
| XTTS-v2 | sim | sim | CPML (restrição comercial) | **descartado** |

## Hardware
VPS: ~268 MB de RAM livre e swap alto (registro de 10/10) — **não hospeda** o gerador. PC do titular (Ryzen 7 5700X, 32 GB, RTX 3060 12 GB): suficiente para os dois candidatos (sem benchmark oficial; medir).

## O que continua NÃO verificado
Texto da licença dos pesos (HF); VRAM/tempo reais; qualidade em pt-BR com a voz do titular; nome exato e revisão do repositório do pacote pt-br; discussões de Reddit/fóruns (bloqueados); suporte a português do CosyVoice 3 e do Pocket TTS na fonte primária.

## Caminho recomendado (sem mudar o serviço já testado)
1. No PC do titular: baixar `ResembleAI/chatterbox` (multilíngue) e o pacote pt-br; gerar as mesmas 3 frases com `make_samples.py` em: multilíngue `pt` (cfg 0,5), multilíngue `pt` (cfg 0), pacote pt-br, Qwen3-TTS 1,7B; o titular escuta às cegas e escolhe. Medir com `measure.py`.
2. Só então adaptar `chatterbox_engine.py` ao pacote vencedor (parâmetro de repositório de pesos e `cfg_weight` configuráveis).
3. Voz sintética identificada, consentimento do titular por perfil (já exigido pelo serviço), PerTh mantida.
