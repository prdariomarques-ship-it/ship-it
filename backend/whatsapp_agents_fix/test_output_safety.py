"""Regression tests for the output-safety barrier (last point before
transport). Pure Python, no DB/app dependencies."""

import pytest
from output_safety import output_safe

# The exact string from the incident (job 20585 / message 9194).
_REAL_MARKER = "[Áudio enviado pelo proprietário desta conta nesta conversa]"


def test_blocks_the_exact_incident_marker():
    reply = f"{_REAL_MARKER}\nClaro, posso te ajudar com isso!"
    result = output_safe(reply)
    assert result.safe is False
    assert result.reason == "internal_marker"


def test_blocks_whole_message_not_just_the_marker_substring():
    # The requirement is explicit: block entirely, do not strip-and-send.
    reply = f"{_REAL_MARKER}\nO produto está disponível, sim."
    result = output_safe(reply)
    assert result.safe is False
    # (there is no "cleaned" text returned anywhere in this API on purpose)


@pytest.mark.parametrize(
    "variant",
    [
        "[Áudio enviado pelo proprietário desta conta nesta conversa]",
        "[audio enviado pelo proprietario desta conta nesta conversa]",
        "[AUDIO ENVIADO PELO PROPRIETARIO]",
        "[Áudio  enviado   pelo proprietário]",  # extra internal spacing
        "[ audio enviado pelo proprietario ]",  # leading/trailing space
        "[Audio Enviado Pelo Proprietario]",  # mixed case
    ],
)
def test_blocks_accent_and_spacing_variants(variant):
    result = output_safe(f"{variant}\ntexto qualquer")
    assert result.safe is False
    assert result.reason == "internal_marker"


def test_blocks_system_instruction_leak():
    result = output_safe("Você é o assistente automático do Dário, siga estas regras:")
    assert result.safe is False
    assert result.reason == "system_instruction_leak"


def test_blocks_internal_manual_reference():
    result = output_safe("De acordo com o manual interno do produto, o procedimento é...")
    assert result.safe is False


def test_blocks_false_claim_that_owner_already_read_the_message():
    # Merged from the V2 candidate's output_safe; the review explicitly
    # prohibits this kind of unverifiable claim.
    result = output_safe("Oi! Ele já viu sua mensagem e vai te responder.")
    assert result.safe is False
    assert result.reason == "unverifiable_read_claim"


def test_blocks_dario_leu_sua_mensagem_variant():
    result = output_safe("Dario leu sua mensagem, só um momento.")
    assert result.safe is False
    assert result.reason == "unverifiable_read_claim"


def test_does_not_block_unrelated_use_of_viu():
    result = output_safe("Já viu nosso catálogo novo?")
    assert result.safe is True


def test_blocks_openrouter_style_key():
    result = output_safe("aqui esta: sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789")
    assert result.safe is False
    assert result.reason == "credential_pattern"


def test_ordinary_reply_is_safe():
    result = output_safe("Oi! Temos o thinner 5L disponível, R$ 45,00. Quer que eu separe um pra você?")
    assert result.safe is True


def test_empty_reply_is_safe_noop():
    assert output_safe("").safe is True
    assert output_safe("   ").safe is True


def test_legitimate_brackets_not_blocked():
    # A client-facing message that happens to use brackets for emphasis
    # must not be caught by an over-broad pattern.
    result = output_safe("Promoção [só esta semana]: tinta 18L com 10% off.")
    assert result.safe is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
