# Mudança 2 (parte A) — patch sobre a produção, sem migração de banco

Autorizada pelo dono em 14/10/2026 ("pode realizar a mudança de dois e a mudança de três"). Executada pelo dono na VPS.
**Revisada em 14/10 (parecer `PARECER_MUDANCA2A_7b73c9e`):** os pontos 1, 2 e 3 foram corrigidos; ver "Correções do parecer".

## O que muda (só `jobs/handlers.py` e `services/messaging.py` do container do backend)
1. **Eco antes da gravação deixa de virar "humano".** O envio guarda o id do WhatsApp devolvido pelo gateway (`key.id`). Se o eco
   (`fromMe`) já tinha gravado a linha como humana, ela é corrigida para "do app" em vez de duplicada. Sem coluna nova.
2. **Pausa de 30 min quando uma PESSOA atua** na conversa (contato + instância): Twin, Loja, B2B, Azusa e pipeline geral. Apresentações do
   próprio robô gravadas como humanas não contam.
3. **Descarte no envio** se uma pessoa escreveu depois de o agente começar a gerar a resposta (`_guard_started_at`/`_guard_contact_id`).
4. **Áudio suspeito não vira resposta:** Twin — menos de 5 palavras, frase típica de alucinação do Whisper ou repetição em laço vira alerta
   ao dono ("responda você mesmo"), sem resposta ao contato; Loja — só frase de alucinação/laço, silêncio com registro.
5. **Dado de contato inventado não sai** pelo Twin: e-mail, link e telefone/documento são comparados **inteiros** com a conversa e com a lista
   permitida (`TWIN_ALLOWED_CONTACT_DATA`, padrão `dariomneto@hotmail.com`).

## Chave de pausa (sem reiniciar)
Arquivo `/app/human_pause_minutes.txt` dentro do container (ou o caminho em `HUMAN_PAUSE_FILE`; senão `HUMAN_PAUSE_MINUTES`; padrão 30).
- desligar: `docker exec darioos-evolution-backend-1 sh -c "echo 0 > /app/human_pause_minutes.txt"`
- religar:  `docker exec darioos-evolution-backend-1 sh -c "echo 30 > /app/human_pause_minutes.txt"`
`0` desliga **a pausa inicial e também a guarda de descarte no envio**. O arquivo vive na camada gravável do container: se o container for
recriado, volta ao padrão de 30.

## Correções do parecer (14/10)
1. **E-mail liberado por comparação de trecho** — confirmado e corrigido. A comparação era por substring; liberava também link que fosse prefixo
   de um permitido e número que fosse sufixo de outro. Agora compara endereço, link e número inteiros (DDI 55 normalizado). Regressões:
   `test_email_e_comparado_inteiro`, `test_link_e_numero_tambem_sao_comparados_inteiros`; três mutantes novos mortos.
2. **Atualização parcial / aplicação frágil** — `scripts-aplicacao/aplicar_na_vps.sh` copia para nomes temporários, confere o SHA-256
   completo **dentro do container**, troca os dois arquivos juntos (cópia de segurança no container), só então reinicia, espera `healthy`,
   roda uma verificação funcional (assinatura do envio, os predicados e duas consultas reais ao banco), confere hashes e `Traceback` nos logs
   **desde o reinício**, e **reverte sozinho** se qualquer etapa falhar. `rollback_na_vps.sh` faz o caminho inverso com as mesmas conferências.
   `scripts-aplicacao/harness.sh` testa essa lógica com um `docker` de mentira em 8 cenários (sucesso; verificação funcional falha; container
   diferente do esperado; cópia corrompida; segundo `mv` falha; não fica `healthy`; `Traceback` nos logs; rollback).
3. **Evidência reproduzível** — `bases-producao/` versiona os 8 arquivos de produção usados (SHA-256 em `SHA256SUMS`);
   `rodar_testes_sobre_producao.sh` aplica o patch, monta a cópia do backend com as bases por cima e roda os testes; o CI executa esse
   script (passo "Mudança 2A sobre os arquivos de produção").
4. **Chave `0`** passa a desligar também o descarte no envio (documentado acima); comandos de ligar/desligar completos.
5. **SHA-256 completo** em todos os scripts. O hotpatch continua na camada gravável do container: **incorporar à imagem/versionamento
   normal é um item aberto** (quadro, G03).

## Como foi verificado
- 29 testes (`test_m2a_producao.py`) sobre as bases de produção já corrigidas; oito mutantes (pausa desligada, sem descarte no envio, eco não
  corrigido, dado inventado liberado, áudio curto liberado, e-mail por sufixo, link por prefixo, chave 0 sem efeito no descarte) são mortos.
- O script do patch só grava se cada trecho existir exatamente uma vez e se o resultado tiver o SHA-256 testado.

## O que NÃO está provado
- Comportamento no PostgreSQL e no Evolution reais; o portão de risco de produção (`orchestrator/twin_risk_gate.py`) não estava na cópia
  (dublê com a assinatura de produção nos testes). A verificação funcional do script de aplicação faz consultas reais ao banco, mas não
  envia mensagem.
- Mensagens da Loja automatizadas por outros caminhos (pós-venda) e gravadas como humanas ainda contariam como "pessoa atuou"; por isso existe
  a chave de pausa.
