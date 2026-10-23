# Inversão de papéis do Gêmeo (caso "Gerente LIBINA", msg 15424) — para revisão

Branch `fix/twin-role-inversion` (a partir de `feat/vendedor-ativo-voz`; o `master` não tem o Gêmeo). **Nada aplicado na VPS, em produção, no banco, no catálogo, em credenciais ou webhooks. Nenhuma mensagem enviada.**

## O que eu não consegui ler (e por quê importa)
- `backend/agents/prompts/darius_twin.md`, `twin_conversation.md` e `backend/orchestrator/twin_policy.py` **não existem neste repositório** (só em produção). Não vi o prompt real nem a política real.
- `handlers.py:388` é a numeração do arquivo de **produção**. No repositório o mesmo trecho está em `backend/jobs/handlers.py:846` (função `twin_autopilot_check`). `agents/darius_twin.py` daqui não tem o mesmo hash do de produção; qualquer aplicação deve ser por edições ancoradas no arquivo de produção, não por cópia.
- Não tenho a mensagem 15424 nem o que o Gêmeo recebeu naquela hora (texto exato do contato, exemplos de estilo recuperados). Os exemplos recuperados não são registrados em log. **A causa abaixo é demonstrada no código e no contexto montado; não foi reproduzida com o LLM real.**

## Causa raiz
Os dois suspeitos da sua hipótese são reais e se somam; nenhum dos dois está sozinho comprovado como "o" gatilho do dia 15424:
1. **Histórico sem autoria** — `backend/jobs/handlers.py:846` (antes): `role='user' if INBOUND else 'assistant'`. Toda saída (o que o dono digitou, o que o próprio Gêmeo respondeu, qualquer outra) virava `assistant`. O Gêmeo não distinguia o que "ele" disse do que o dono disse.
2. **Outras conversas entram sem dono** — `backend/services/style_context.py:24` (`format_style_block`). Os únicos trechos de outras conversas no Gêmeo, neste código, são os exemplos "Pergunta/Resposta" (`style_distill.build_example`). O cabeçalho dizia "como o Dário respondeu a mensagens parecidas" e **não** dizia que a Pergunta é de outra pessoa nem que nada ali descreve o interlocutor atual. Pior: `HEADER_RULES` manda não repetir "informações de nenhuma pessoa que apareça neles", o que conflita com a sua decisão de usar fatos do próprio dono. Um exemplo do tipo "Pergunta: melhorou? / Resposta: Ainda não... Vc tá melhorando aí?" (o dono perguntando de volta a OUTRA pessoa) ensina exatamente o padrão do bug.
3. **O prompt não diz quem é o sujeito** — `backend/agents/darius_twin.py:70` só informa "Você está respondendo para: {nome}". Nada diz que "você melhorou?" do interlocutor é sobre o dono. (O texto real do `.md` de produção eu não vi.)

## O que mudou (evolução, sem recriar)
| Arquivo | Mudança |
|---|---|
| `backend/agents/darius_twin_roles.py` (novo, puro, sem I/O) | `build_twin_history` (rótulos `[Dário]`/`[Gêmeo]`), `ROLE_RULES`, notas dos exemplos, `guard_role_inversion` |
| `backend/jobs/handlers.py:846` | a lista inline vira `build_twin_history(history, content_of=_owner_audio_history_content, exclude_id=message_id)` (conteúdo e filtros iguais; só acrescenta o rótulo) |
| `backend/agents/darius_twin.py` | `load_persona_prompt` termina com `ROLE_RULES`; a linha do contato diz "NÃO é o Dário"; a resposta passa por `guard_role_inversion` |
| `backend/services/style_context.py` | o cabeçalho dos exemplos diz que são de OUTRA conversa; só no Gêmeo, exceção expressa para fatos do próprio dono |

Compatibilidade preservada: mesma ordem e contagem de mensagens de sistema (o teste existente `test_twin_recebe_os_blocos_extras_como_mensagens_de_sistema` continua igual), `HEADER_RULES` intacto, assinatura de `generate_darius_reply` intacta, histórico de entrada igual. Sem coluna nova, sem migration.

**Rede de segurança determinística** (`guard_role_inversion`): só age quando o contato **perguntou pela saúde do dono** E **nunca disse estar doente** (mensagem atual ou histórico). Aí remove da resposta apenas as perguntas de saúde dirigidas a ele (ex.: "Vc tá melhorando aí?"). As afirmações sobre o dono ficam intactas. Se a resposta inteira era só isso, vira `TwinReplyUnavailable` → retenção neutra já existente (nunca um texto invertido). Remove também marcadores `[Dário]`/`[Gêmeo]` que o modelo copiar.

## Limites conhecidos (honestos)
- A rede usa expressões regulares em português informal: pode falhar em redações incomuns. O erro seguro é remover a pergunta (perde-se uma frase), nunca inventar.
- Não cobre outras inversões (ex.: "Que bom que você melhorou!" dito pelo Gêmeo). Essas dependem do prompt, que agora tem a regra, mas sem garantia determinística.
- O LLM real não foi chamado; os testes provam o contexto montado e o tratamento da resposta.

## Privacidade (NÃO implementado — aguardo seu aval)
Fatos sobre **terceiros** vindos de outra conversa não devem aparecer para outro contato. Hoje o único canal é o exemplo de estilo (cabeçalho manda não repetir nomes/dados, mas é só instrução). Opções para decidir:
- **A.** Só reforçar a instrução (já feito no cabeçalho). Barato, sem garantia.
- **B.** Filtro na destilação (`style_distill`): não guardar pares cuja Resposta cite nome/telefone/valor de terceiro. Garantia melhor, perde alguns exemplos; exige reindexar.
- **C.** Filtro na hora de usar: descartar exemplos com entidades que não pertencem ao contato atual. Mais preciso, mais código e mais falsos descartes.
Recomendo B + A. Fatos do próprio dono continuam permitidos em qualquer opção.

## Rollback
- Nada está aplicado; o rollback do código é `git revert` do(s) commit(s) da branch (ou simplesmente não mesclar).
- Para a VPS (futuro, só com seu aval): usar o padrão já adotado — backup dos 4 arquivos no container, cópia atômica, reinício, verificação, volta automática se falhar. Restaurar = recolocar os originais e reiniciar. Sem migration, nada a reverter no banco.
- Interruptor rápido, se preferir (não incluído; diga se quer): variável de ambiente que desliga só a rede de segurança sem redeploy.
