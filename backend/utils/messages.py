"""Mensagens de erro voltadas ao usuário final, centralizadas em PT-BR.

Release 1.5 hardening (achado do red-team audit): o `detail` de uma
`HTTPException` chega ao frontend e é exibido diretamente ao usuário --
antes desta mudança, esse texto estava em inglês, misturado a uma UI
inteiramente em português. Logs e exceções internas (o que nunca chega ao
`detail` de uma resposta HTTP) continuam em inglês, por convenção do
projeto -- este módulo cobre exclusivamente texto que o usuário final pode
ver, não texto de depuração.

Escopo desta rodada: apenas `api/contact_workspace.py` (onde o achado do
audit se originou). Uma varredura de todo o backend por mensagens em
inglês está fora de escopo aqui -- ver `docs/TECHNICAL_DEBT.md`.
"""

CONTACT_NOT_FOUND = "Contato não encontrado."

RECOMMENDATION_EXPIRED = (
    "Esta recomendação não é mais válida -- o sinal que a gerou não está "
    "mais presente."
)

RECOMMENDATION_NOT_EXECUTABLE = "Esta recomendação não possui uma ação executável."


def tool_not_registered(tool_name: str) -> str:
    """A ferramenta referenciada pela recomendação não está registrada no
    Tool Registry -- sempre um bug de configuração, nunca um estado
    alcançável por uso normal, mas ainda assim visível ao usuário final se
    ocorrer, então também traduzido."""
    return f"A ferramenta {tool_name!r} não está registrada."
