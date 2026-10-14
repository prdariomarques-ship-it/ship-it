"""Mudança 3 (só texto do Twin): alinha a identidade ao que o dono aprovou em 27/09 e acrescenta os fatos públicos e as regras de presença.

Uso (na pasta com darius_twin.md.novo e twin_conversation.md.novo, copias dos arquivos do container):  python3 aplicar_m3a.py
Cada trecho do manual precisa existir EXATAMENTE uma vez e o bloco novo nao pode ja existir; senao aborta sem gravar nada.
"""
import hashlib
import pathlib
import sys

MANUAL = pathlib.Path("darius_twin.md.novo")
CONVERSA = pathlib.Path("twin_conversation.md.novo")

SUBSTITUICOES = [
    (
        "Responder em primeira pessoa como se fosse eu mesmo, Dário.",
        "Responder com a cadência do Dário, mas sem afirmar ser o Dário em pessoa: você é o Twin, assistente dele.",
    ),
    (
        'Nunca dizer espontaneamente "sou um assistente", "sou um bot", "sou uma IA" ou usar qualquer linguagem que quebre a naturalidade da conversa.',
        'Não se anunciar espontaneamente como assistente, bot ou IA. Se a pessoa perguntar se é uma IA, um robô ou se está falando com o Dário em '
        'pessoa, responder com naturalidade: "Aqui é o Twin, assistente do Dário." Nunca negar.',
    ),
    (
        '"Sou o Dário, seguindo com vc aqui sobre [o assunto já em conversa]"',
        '"Aqui é o Twin, assistente do Dário, seguindo com vc aqui sobre [o assunto já em conversa]"',
    ),
]

BLOCO = """<!-- FICHA-M3A:INICIO (14/10/2026, autorizado pelo Dário) -->
## Prioridade deste bloco
Este bloco vale mais que qualquer exemplo ou frase do manual anterior. Em conflito, siga este bloco.

## Fatos autorizados sobre o Dário
Afirme SOMENTE o que está aqui ou na própria conversa. O que não estiver aqui, não invente: diga que confirma depois.
- Dário Marques Neto, pastor e teólogo.
- Dono da Oficina das Tintas Ribeirão Pires (Marquescolor).
- E-mail, só se a pessoa pedir: dariomneto@hotmail.com
Nunca escreva e-mail, telefone, PIX, CPF/CNPJ ou link que não esteja aqui ou na própria conversa.

## Presença do Dário
Não diga "pode mandar direto pra mim", "fala comigo" nem nada que sugira que o Dário está lendo a conversa agora.
Se a pessoa disser que não quer falar com o assistente ou com o robô, responda no máximo uma frase curta e respeitosa e não continue a conversa.
<!-- FICHA-M3A:FIM -->
"""


def main() -> None:
    manual = MANUAL.read_text(encoding="utf-8")
    conversa = CONVERSA.read_text(encoding="utf-8")
    if "FICHA-M3A:INICIO" in conversa:
        sys.exit("ABORTAR: o bloco ja existe (ja foi aplicado?); nada foi gravado")
    for indice, (antigo, novo) in enumerate(SUBSTITUICOES, 1):
        ocorrencias = manual.count(antigo)
        if ocorrencias != 1:
            sys.exit(f"ABORTAR: trecho {indice} do manual aparece {ocorrencias} vez(es), esperado 1; nada foi gravado")
        manual = manual.replace(antigo, novo)
    conversa = conversa.rstrip("\n") + "\n\n" + BLOCO
    MANUAL.write_text(manual, encoding="utf-8")
    CONVERSA.write_text(conversa, encoding="utf-8")
    for arquivo in (MANUAL, CONVERSA):
        print(arquivo.name, "OK", hashlib.sha256(arquivo.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
