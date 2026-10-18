"""ChatRequest: clientes antigos continuam aceitos; campos exclusivos de /chat/ocr são recusados (422) antes de qualquer agente."""
import pytest
from pydantic import ValidationError

from chat.schemas import ChatRequest, OCRChatRequest


def test_legacy_client_with_unknown_extra_field_is_still_accepted():
    req = ChatRequest(**{"message": "oi", "agent": "assistant", "contact_id": 3, "client_version": "1.2", "debug": True})
    assert (req.message, req.agent, req.contact_id) == ("oi", "assistant", 3)
    assert not hasattr(req, "client_version")


@pytest.mark.parametrize("field,value", [("ocr_source_message_id", 19), ("expected_instance", "inst")])
def test_ocr_only_fields_on_plain_chat_are_rejected(field, value):
    with pytest.raises(ValidationError) as exc:
        ChatRequest(**{"message": "Explique este documento.", "contact_id": 7, field: value})
    assert "/chat/ocr" in str(exc.value)


def test_ocr_request_still_forbids_extras_and_requires_exact_fields():
    ok = {"message": "x", "contact_id": 7, "ocr_source_message_id": 19, "expected_instance": "inst"}
    assert OCRChatRequest(**ok).expected_instance == "inst"
    with pytest.raises(ValidationError):
        OCRChatRequest(**ok, agent="assistant")
    with pytest.raises(ValidationError):
        OCRChatRequest(**{**ok, "expected_instance": ""})
