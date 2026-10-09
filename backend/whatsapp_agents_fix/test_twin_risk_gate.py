"""Regression tests for orchestrator/twin_risk_gate.py.

Pure-Python, no DB/app dependencies -- runs standalone. Covers the two
incidents from the 08/10/2026 WhatsApp review: the "a culpa nao e nossa"
denial re-triggering crisis on every later message, and "separar os
produtos" being classified the same as a personal separation.
"""

from datetime import datetime, timezone

import pytest
from twin_risk_gate import (
    HistoryEntry,
    MessageAuthor,
    classify_text,
    group_for_snippet,
    is_high_risk_for_impersonation,
)

NOW = datetime(2026, 10, 8, 18, 16, 34, tzinfo=timezone.utc)


def test_plain_crisis_word_still_escalates_recall_preserved():
    # Negative control: nothing in the fix should have narrowed recall on an
    # actual unqualified hit.
    result = is_high_risk_for_impersonation(9030, "to desanimando com tudo isso", [])
    assert result is not None
    assert result.category == "crise"
    assert result.snippet == "desanimando"
    assert result.in_current_message is True
    assert result.source_author == MessageAuthor.CLIENT


def test_culpa_without_negation_still_escalates():
    result = is_high_risk_for_impersonation(1, "a culpa e toda minha", [])
    assert result is not None
    assert result.category == "crise"
    assert result.snippet == "culpa"


def test_culpa_negated_does_not_escalate_message_9212_scenario():
    # The exact incident: an outbound audio transcript from the owner,
    # "A culpa não é nossa", sitting in history must not flag the client.
    history = [
        HistoryEntry(9212, MessageAuthor.OWNER, NOW, "A culpa não é nossa"),
    ]
    result = is_high_risk_for_impersonation(9300, "oi, bom dia", history)
    assert result is None


def test_stale_negated_history_does_not_keep_retriggering():
    # This is the 9030/9031 + 9096/9097 repetition: the same old denial
    # must not cause a fresh escalation on every subsequent routine message.
    history = [
        HistoryEntry(9212, MessageAuthor.OWNER, NOW, "A culpa não é nossa"),
    ]
    for routine_text in ("oi", "ok", "tudo bem, obrigado", "pode ser amanhã?"):
        assert is_high_risk_for_impersonation(9999, routine_text, history) is None


def test_separar_produtos_is_business_context_not_personal_crisis():
    result = is_high_risk_for_impersonation(1, "quero separar os produtos pro pedido", [])
    assert result is None


def test_separar_without_business_object_still_escalates():
    # "separar" alone (no product/order/stock word nearby) keeps its
    # original broad recall -- only the business-object exception is new.
    result = is_high_risk_for_impersonation(1, "acho que vou separar", [])
    assert result is not None
    assert result.category == "crise"
    assert result.snippet.startswith("separa")


def test_history_hit_from_owner_is_attributed_to_owner_not_client():
    history = [
        HistoryEntry(500, MessageAuthor.OWNER, NOW, "to muito cansado hoje"),
    ]
    result = is_high_risk_for_impersonation(9999, "ok entao", history)
    assert result is not None
    assert result.source_author == MessageAuthor.OWNER
    assert result.source_message_id == 500
    assert result.in_current_message is False
    assert "proprietário" in result.reason()


def test_context_continuity_preserved_ok_pode_ser_example_from_docstring():
    # The module's own stated design goal: "ok, pode ser" after a sensitive
    # thread must still escalate -- context coverage was not weakened.
    history = [
        HistoryEntry(1, MessageAuthor.CLIENT, NOW, "nao aguento mais essa situacao"),
    ]
    result = is_high_risk_for_impersonation(2, "ok, pode ser", history)
    assert result is not None
    assert result.category == "crise"


def test_financial_terms_no_longer_escalate():
    assert classify_text("quero investir em acoes") == ("financeiro", "investir")
    result = is_high_risk_for_impersonation(1, "quero investir em acoes", [])
    assert result is None


def test_negation_does_not_over_trigger_on_unrelated_later_clause():
    # "nao" negates "melhore", not "medo" -- a real signal must not be
    # cleared just because some later word in the sentence is negated.
    result = is_high_risk_for_impersonation(1, "tenho medo que isso nao melhore", [])
    assert result is not None
    assert result.snippet == "medo"


def test_negation_before_the_term_still_clears_it():
    result = is_high_risk_for_impersonation(1, "nao tenho medo disso", [])
    assert result is None


def test_nao_aguento_mais_is_never_cancelled_by_its_own_nao():
    # "nao aguento" is the signal, not a negation of suffering.
    result = is_high_risk_for_impersonation(1, "nao aguento mais essa situacao", [])
    assert result is not None
    assert result.category == "crise"
    assert result.snippet == "nao aguento mais"


def test_nao_aguento_mais_not_cancelled_by_unrelated_later_clause():
    # Real bug found in review: a later, separate clause's own negation
    # ("isso nao e facil") must not reach back across the comma and clear
    # the earlier crisis phrase.
    result = is_high_risk_for_impersonation(
        1, "nao aguento mais, isso nao e facil pra ninguem", []
    )
    assert result is not None
    assert result.snippet == "nao aguento mais"


def test_negation_does_not_cross_a_clause_boundary_before_the_term():
    # An earlier clause's negation must not reach forward across a comma
    # to cancel an unrelated later signal.
    result = is_high_risk_for_impersonation(1, "nao sei o que fazer, tenho medo", [])
    assert result is not None
    assert result.snippet == "medo"


def test_after_negation_still_works_within_the_same_clause():
    # Regression guard: the clause-boundary fix must not break the original
    # "a culpa nao e nossa" case, which has no punctuation between the term
    # and its negator.
    result = is_high_risk_for_impersonation(1, "a culpa nao e nossa", [])
    assert result is None


def test_sem_crise_colloquial_reassurance_does_not_escalate():
    # Real gap found in review: "sem crise" is a common Brazilian Portuguese
    # reassurance ("no worries"), not a crisis disclosure -- e.g. a client
    # asking "voce pode ir na minha casa?" and getting "sem crise, vou sim".
    result = is_high_risk_for_impersonation(1, "sem crise, vou sim", [])
    assert result is None


def test_sem_crise_mid_sentence_still_does_not_escalate():
    result = is_high_risk_for_impersonation(1, "pode vir, sem crise", [])
    assert result is None


def test_sem_does_not_broaden_into_the_general_negation_window():
    # "sem" must only cancel "crise" when immediately adjacent to it -- it
    # must NOT be added to the general 3-word negation window. "sem razao"
    # here negates "razao" (reason), not "me matar" -- but "sem" still
    # falls within 3 words of "me matar", so if "sem" were a general
    # negator this genuine signal would be wrongly cleared.
    result = is_high_risk_for_impersonation(1, "sem razao quero me matar", [])
    assert result is not None
    assert result.category == "crise"
    assert result.snippet == "me matar"


def test_business_sale_still_escalates():
    result = is_high_risk_for_impersonation(1, "quero vender a loja", [])
    assert result is not None
    assert result.category == "negocio"


def test_informational_address_repass_exception_still_works():
    result = is_high_risk_for_impersonation(1, "pode repassar o endereco da igreja?", [])
    assert result is None


def test_evidence_reason_never_includes_full_message_only_snippet():
    history = [
        HistoryEntry(42, MessageAuthor.CLIENT, NOW, "sinto muito medo e muita culpa, nao aguento"),
    ]
    result = is_high_risk_for_impersonation(9999, "oi", history)
    assert result is not None
    assert result.snippet in {"medo", "culpa", "nao aguento mais"} or len(result.snippet) < 20
    assert "sinto muito medo e muita culpa" not in result.reason()


def test_crying_paraphrases_share_the_same_evidence_group():
    # "chorei" (cried) and "chorando"/"choran*" (crying) are the SAME
    # statement reworded -- must collapse to one group so a reword alone
    # does not look like new evidence to incident_dedup.py.
    assert group_for_snippet("chorei") == group_for_snippet("chorando")
    assert group_for_snippet("chorar") == group_for_snippet("chorei")


def test_suicide_ideation_paraphrases_share_the_same_evidence_group():
    assert group_for_snippet("quero morrer") == group_for_snippet("suicidio")
    assert group_for_snippet("acabar com minha vida") == group_for_snippet("quero morrer")


def test_unrelated_terms_are_different_groups():
    # "culpa" (guilt) and "quero morrer" (suicidal ideation) must NOT
    # collapse -- moving from one to the other is exactly the "genuinely
    # new, more severe" case that must still be allowed to re-alert.
    assert group_for_snippet("culpa") != group_for_snippet("quero morrer")
    assert group_for_snippet("medo") != group_for_snippet("chorei")


def test_unknown_snippet_falls_back_to_itself_not_merged_with_anything():
    # A snippet that matched CRISIS_PATTERN but isn't in any explicit group
    # (e.g. "culpa", "medo", "vazio" -- single-word terms with no listed
    # paraphrase) must never be silently treated as equivalent to some
    # other unrelated snippet.
    assert group_for_snippet("culpa") == "culpa"
    assert group_for_snippet("vazio") == "vazio"
    assert group_for_snippet("culpa") != group_for_snippet("vazio")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
