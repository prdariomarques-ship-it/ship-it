"""Plugin de pytest: com REQUIRE_POSTGRES_TESTS=1, pular um teste que depende de PostgreSQL FALHA a execução.

Os testes de concorrência reais (fechamento de entrega incerta, claim de acompanhamento, cadeia de migrações, deduplicação) são
pulados quando `TEST_POSTGRES_URL` / `WHATSAPP_DEDUP_PG_ADMIN_URL` não estão definidas. Localmente isso é desejável; no CI uma
variável que sumiu transformaria a prova de concorrência em skip silencioso e o job ficaria verde. `-rs` só lista os pulados: esta
guarda é o que faz o CI quebrar.

Uso (CI):  REQUIRE_POSTGRES_TESTS=1 python -m pytest -q -rs -p ci_require_postgres
O critério é o MOTIVO do skip citar uma das variáveis abaixo; skips por outro motivo continuam permitidos."""
import os

import pytest

ENV_FLAG = "REQUIRE_POSTGRES_TESTS"
POSTGRES_ENV_VARS = ("TEST_POSTGRES_URL", "WHATSAPP_DEDUP_PG_ADMIN_URL")
_skipped: list[tuple[str, str]] = []


def _active() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


def pytest_runtest_logreport(report):
    if not report.skipped or not _active():
        return
    longrepr = report.longrepr
    reason = str(longrepr[2]) if isinstance(longrepr, tuple) and len(longrepr) == 3 else str(longrepr)
    if any(name in reason for name in POSTGRES_ENV_VARS):
        _skipped.append((report.nodeid, reason))


def pytest_terminal_summary(terminalreporter):
    if _skipped:
        terminalreporter.section(f"{ENV_FLAG}=1: testes PostgreSQL pulados (isto é uma falha)", red=True)
        for nodeid, reason in _skipped:
            terminalreporter.line(f"{nodeid}: {reason}")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if _skipped and _active() and exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
