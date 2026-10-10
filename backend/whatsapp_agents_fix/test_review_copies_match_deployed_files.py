"""This review package necessarily keeps a few copies of the same pure
logic, for reasons Python's import system forces on us (see
conftest.py's module docstring): a flat-import copy for the simple
logic tests, a package-qualified copy inside app_stub/ for the handler-
execution tests, and the real, canonically-deployed file at its real
backend/ path, with one deliberate difference (import style).

This test is what keeps that duplication honest: if any copy drifts
from the others in anything OTHER than that one documented import line,
this fails loudly, in CI, not silently in review.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent
BACKEND_ROOT = HERE.parents[0]


def _read(path: Path) -> str:
    return path.read_text()


def _strip_import_line(text: str, flat_import: str, qualified_import: str) -> str:
    """Normalizes the one documented, intentional difference (flat vs.
    package-qualified import of twin_risk_gate) so the rest of the file
    can be compared verbatim."""
    return text.replace(qualified_import, flat_import)


def test_twin_risk_gate_harness_copy_matches_deployed_file_exactly():
    deployed = _read(BACKEND_ROOT / "orchestrator" / "twin_risk_gate.py")
    harness = _read(HERE / "twin_risk_gate.py")
    assert deployed == harness


def test_output_safety_harness_copy_matches_deployed_file_exactly():
    # Review fix (regression round): output_safety.py no longer imports
    # anything from orchestrator.twin_risk_gate at all -- it has its own,
    # deliberately separate normalize_text (see its module docstring for
    # why sharing one with twin_risk_gate caused a real regression). No
    # import-style difference is left to normalize; this is back to a
    # plain exact-match comparison, same as before (E) ever existed.
    deployed = _read(BACKEND_ROOT / "services" / "output_safety.py")
    harness = _read(HERE / "output_safety.py")
    assert deployed == harness


def test_incident_dedup_harness_copy_matches_deployed_file_except_the_documented_import_line():
    deployed = _read(BACKEND_ROOT / "orchestrator" / "incident_dedup.py")
    harness = _read(HERE / "incident_dedup.py")
    normalized_deployed = _strip_import_line(
        deployed,
        flat_import="from twin_risk_gate import RiskEvidence, group_for_snippet",
        qualified_import="from orchestrator.twin_risk_gate import RiskEvidence, group_for_snippet",
    )
    assert normalized_deployed == harness


def test_app_stub_orchestrator_copies_match_the_harness_root_copies():
    # app_stub/orchestrator/ needs package-qualified-style copies (to
    # satisfy the real handlers.py's `from orchestrator.X import Y`
    # when loaded through the stub tree) -- these must still be the
    # SAME content as the deployed files, i.e. identical to each other
    # minus nothing (both are package-qualified already).
    for name in ("incident_dedup.py", "twin_risk_gate.py"):
        deployed = _read(BACKEND_ROOT / "orchestrator" / name)
        stub_copy = _read(HERE / "app_stub" / "orchestrator" / name)
        assert deployed == stub_copy, f"app_stub/orchestrator/{name} has drifted from the deployed file"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
