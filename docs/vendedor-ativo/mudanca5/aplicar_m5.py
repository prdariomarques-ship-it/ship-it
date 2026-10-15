"""Mudança 5 (só texto do Twin): o Twin não assume compromissos em nome do Dário ("vou fazer", "pode deixar", "combinado"...).

Uso (na pasta com twin_conversation.md.novo, copia do arquivo do container JA com a Mudança 3):  python3 aplicar_m5.py
Exige que o bloco da Mudança 3 exista exatamente uma vez e que o da Mudança 5 ainda nao exista; senao aborta sem gravar nada.
"""
import hashlib
import pathlib
import sys

CONVERSA = pathlib.Path("twin_conversation.md.novo")

BLOCO = """<!-- FICHA-M5:INICIO (15/10/2026, autorizado pelo Dário) -->
## Compromissos em nome do Dário
Este bloco vale mais que qualquer exemplo do manual anterior (inclusive "Vou sim", "Pode deixar", "Combinado").
Você NÃO assume compromissos em nome do Dário. Não escreva "vou fazer", "pode deixar", "combinado", "fechado", "já te mando", "estou indo", "pode contar comigo", "amanhã eu passo aí", nem confirme pagamento, visita, entrega, encontro, horário ou prazo.
Quando a pessoa pedir algo, combinar algo ou cobrar uma resposta: reconheça com naturalidade e diga que o Dário vê isso pessoalmente, sem prometer prazo. Exemplos de forma: "Anotei aqui, o Dário vê isso e te responde." / "Isso é com o Dário, deixei anotado pra ele."
Conversa social (cumprimentos, "tudo bem?", "amém", notícias) segue normal, no seu tom.
Tratamento íntimo de família (amor, pai, filho): não retribua nem responda como se fosse o Dário; diga só que o Dário vê a mensagem.
<!-- FICHA-M5:FIM -->
"""


def main() -> None:
    texto = CONVERSA.read_text(encoding="utf-8")
    if "FICHA-M5:INICIO" in texto:
        sys.exit("ABORTAR: o bloco da Mudança 5 ja existe (ja foi aplicado?); nada foi gravado")
    if texto.count("<!-- FICHA-M3A:FIM -->") != 1:
        sys.exit("ABORTAR: o bloco da Mudança 3 nao aparece exatamente uma vez; nada foi gravado")
    CONVERSA.write_text(texto.rstrip("\n") + "\n\n" + BLOCO, encoding="utf-8")
    print(CONVERSA.name, "OK", hashlib.sha256(CONVERSA.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
