"""Mudança 4 (sem migração de banco): contatos "silenciosos" do Twin. Para os contatos listados num arquivo, o Twin NAO responde e o dono recebe o alerta.

Uso (na pasta com handlers.py.novo, copia do /app/jobs/handlers.py do container JA com a Mudança 2A):  python3 aplicar_m4.py
Cada trecho antigo precisa existir EXATAMENTE uma vez; senao aborta sem gravar nada. Confere o sha256 de entrada e de saida.
"""
import hashlib
import pathlib
import sys

NOME = "handlers.py.novo"
HASH_ENTRADA = "bf3ff6b771721ace8bde9cc3e525f80593f4511f2c88c47de4c92fdd438fc117"  # handlers.py de producao depois da Mudanca 2A
HASH_SAIDA = "9eb1e67c626efd3fbcb204e91cb794649be32b7e2e31b0af50d7b0bca64e15b1"  # arquivo exato que passou nos testes

SUBSTITUICOES = [
    (
        '''def _guard_now_iso() -> str:
    from datetime import datetime, timezone
''',
        '''# ---- Mudança 4 (autorizada pelo dono): contatos em que o Twin NUNCA responde (familia, chefes); o dono recebe o alerta ----
def _twin_silent_entries() -> list[str]:
    """Entradas do arquivo (mudavel sem reiniciar): uma por linha ou separadas por virgula; id de contato (ate 7 digitos) ou telefone (qualquer formato); `#` comenta."""
    import os

    try:
        with open(os.environ.get("TWIN_SILENT_FILE", "/app/twin_silent_contacts.txt"), encoding="utf-8") as handle:
            raw = handle.read()
    except OSError:
        return []
    entries: list[str] = []
    for line in raw.splitlines():
        entries.extend(part.strip() for part in line.split("#", 1)[0].split(",") if part.strip())
    return entries


def _twin_silent_contact(contact_id: int, phone) -> bool:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    for entry in _twin_silent_entries():
        wanted = "".join(ch for ch in entry if ch.isdigit())
        if not wanted:
            continue
        if len(wanted) <= 7:
            if int(wanted) == contact_id:
                return True
        elif len(wanted) >= 10 and digits and digits[-11:] == wanted[-11:]:
            return True
    return False


def _guard_now_iso() -> str:
    from datetime import datetime, timezone
''',
    ),
    (
        """    is_risky, reason = is_high_risk_for_impersonation(message.content, history_texts)
""",
        """    is_risky, reason = is_high_risk_for_impersonation(message.content, history_texts)
    silent_contact = _twin_silent_contact(contact_id, contact.phone)
    if silent_contact:
        is_risky, reason = (True, 'contato prioritário (família/chefe): o Twin não responde')
""",
    ),
    (
        """        if settings.whatsapp_owner_alert_phone:
""",
        """        if settings.whatsapp_owner_alert_phone and (not silent_contact or await rate_limiter.is_allowed(f'twin-silent-alert:{instance}:{contact_id}', limit=1, window_seconds=600)):
""",
    ),
]


def main() -> None:
    caminho = pathlib.Path(NOME)
    original = caminho.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest != HASH_ENTRADA:
        sys.exit(f"ABORTAR: {NOME} tem hash {digest}, esperado {HASH_ENTRADA} (o container mudou ou a 2A nao esta aplicada); nada foi gravado")
    texto = original.decode("utf-8")
    for indice, (antigo, novo) in enumerate(SUBSTITUICOES, 1):
        ocorrencias = texto.count(antigo)
        if ocorrencias != 1:
            sys.exit(f"ABORTAR: trecho {indice} aparece {ocorrencias} vez(es), esperado 1; nada foi gravado")
        texto = texto.replace(antigo, novo)
    novo_hash = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    if HASH_SAIDA is not None and novo_hash != HASH_SAIDA:
        sys.exit(f"ABORTAR: resultado tem hash {novo_hash}, esperado {HASH_SAIDA}; nada foi gravado")
    caminho.write_text(texto, encoding="utf-8")
    print(NOME, "OK", novo_hash)


if __name__ == "__main__":
    main()
