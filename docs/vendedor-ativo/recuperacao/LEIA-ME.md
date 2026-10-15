# Recuperação dos patches (Mudanças 2A, 3, 4 e 5)

Os patches vivem na camada gravável do container `darioos-evolution-backend-1` (a imagem é fixa por hash no compose e `/app` não é volume). Se o container for **recriado** (`compose up` com mudança de configuração, `docker rm`, atualização da imagem), voltam os arquivos originais.

`recuperar_patches.sh <pasta da cópia de segurança>` devolve os 4 arquivos (handlers.py, messaging.py, darius_twin.md, twin_conversation.md) e a lista silenciosa. Só age se os 4 do container forem EXATAMENTE os originais conhecidos; confere o hash de cada cópia; reinicia o backend; reverte sozinho se algo falhar. `harness_recuperacao.sh` testa a lógica (8 cenários, docker de mentira).

Limite: depende da cópia de segurança feita com o comando de cópia (pasta `/root/backup_twin_*`). Não substitui incorporar os patches à imagem (G03).
