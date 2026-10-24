# Gêmeo — papéis, silêncio e ato proibido (PRODUÇÃO). Pacote de aplicação (NÃO aplicado)

O que faz, em uma linha cada:
1. **Papéis:** rotula `[Dário]`/`[Gêmeo]` no histórico, põe a regra de papéis no prompt, tira da resposta o apelido que o contato usa para chamar você ("Netinho", "pastor X", "pai") e a pergunta de saúde devolvida a quem não disse estar doente.
2. **Silêncio:** não responde (nem retenção, nem alerta) a robô/menu/fila, alerta do próprio sistema e despedida pura (só se já falamos antes).
3. **Ato proibido:** autorizar/emitir, pedir agência-conta-CPF, cobrar/reembolso, confirmar depósito sem comprovante, assumir prazo, "já segui…" caem no caminho de risco que já existe (retenção silenciosa + alerta ao dono com o rascunho).

Casos reais que motivaram: 223 respostas de 16 a 23/10 — nenhuma seria barrada pelos guardas de produção atuais (financeiro 0, compromisso 0, contraparte automática 2).

## O que o script faz (e garante)
Confere o `SHA256SUMS` da pasta; lê `darius_twin.py` e `jobs/handlers.py` DO container e só segue se forem os originais conhecidos (o `handlers.py` também pode estar com o owner-guard; qualquer outro estado → aborta sem tocar); gera os novos por edições ancoradas; copia para nomes temporários e confere; faz cópia de segurança DENTRO do container; troca; reinicia; espera `healthy`; roda uma verificação funcional que só lê (sem mensagem, sem banco); **qualquer falha devolve tudo e reinicia de novo**. Não sobrescreve cópia de segurança existente.

## Como aplicar (você)
```powershell
# PowerShell do PC (troque o caminho da pasta twin-pacote)
scp -r "C:\caminho\twin-pacote" root@184.107.176.28:/root/
```
```bash
# VPS
cd /root/twin-pacote && sed -i 's/\r$//' *.sh *.py
sha256sum -c SHA256SUMS            # tem que dizer OK nos 4 arquivos
sha256sum SHA256SUMS aplicar_na_vps_twin.sh rollback_twin.sh   # compare com os hashes que recebeu no chat
bash aplicar_na_vps_twin.sh
```
Esperado no fim: `SUCESSO: o Gemeo agora (1) rotula…`. Se aparecer `REVERTIDO`, nada ficou alterado; cole a saída.

## Desfazer
`cd /root/twin-pacote && bash rollback_twin.sh` (devolve os 2 arquivos, remove os 3 módulos, reinicia, espera healthy). Sem rollback de banco: nada é gravado.

## Interruptores (variáveis de ambiente do container; exigem reiniciar)
`TWIN_ROLE_GUARD_ENABLED=false` · `TWIN_ACTION_GUARD=0` · `TWIN_SILENCE=0`.
Pausa quando você fala: já existe em produção (`TWIN_OWNER_PAUSE_MINUTES`, hoje 6). **Subir para 30** é só mudar essa variável — decisão sua.

## Avisos
- Um `docker cp` se perde se o container for **recriado** (só reiniciar mantém). Nunca rode `recreate_container.py`.
- Se aplicar também o **owner-guard** (outro pacote), qualquer ordem funciona (testado nos dois sentidos contra o `handlers.py` real); o resultado é idêntico.
- O harness (`prod/vps/harness_twin.sh`, só no repositório) simula 13 cenários com docker de mentira (não enxerga a espera de health real).
