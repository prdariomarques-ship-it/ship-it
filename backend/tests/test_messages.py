"""utils/messages.py -- Release 1.5 hardening, FIX 3 (backend localization).

Pure string/formatting checks. The 404/400 paths that use these constants
are covered end-to-end in test_contact_workspace.py and
test_contact_recommendations_endpoint.py; this file covers the one path
those integration tests can't reach without invasively mocking the Tool
Registry -- `tool_not_registered`, the 500 path for a recommendation
referencing an unregistered tool (a configuration bug, not a reachable
user flow, but still user-facing text if it ever fires)."""

from utils import messages


def test_contact_not_found_is_portuguese():
    assert messages.CONTACT_NOT_FOUND == "Contato não encontrado."


def test_recommendation_expired_is_portuguese():
    assert "não é mais válida" in messages.RECOMMENDATION_EXPIRED


def test_recommendation_not_executable_is_portuguese():
    assert messages.RECOMMENDATION_NOT_EXECUTABLE == (
        "Esta recomendação não possui uma ação executável."
    )


def test_tool_not_registered_is_portuguese_and_includes_the_tool_name():
    result = messages.tool_not_registered("send_whatsapp")
    assert "não está registrada" in result
    assert "'send_whatsapp'" in result
