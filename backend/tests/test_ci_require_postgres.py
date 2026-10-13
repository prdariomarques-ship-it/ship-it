"""Guarda anti-skip do CI (`ci_require_postgres`): pulado por falta de PostgreSQL só derruba a execução quando REQUIRE_POSTGRES_TESTS=1.
Roda o pytest de verdade em subprocesso, sobre um teste gerado, isolado da configuração do repositório."""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _run(tmp_path, body, *, flag):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_generated.py").write_text(body)
    env = {k: v for k, v in os.environ.items() if k not in ("TEST_POSTGRES_URL", "WHATSAPP_DEDUP_PG_ADMIN_URL", "REQUIRE_POSTGRES_TESTS")}
    env["PYTHONPATH"] = str(BACKEND)
    if flag is not None:
        env["REQUIRE_POSTGRES_TESTS"] = flag
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs", "-p", "ci_require_postgres", "-p", "no:cacheprovider",
                           "-c", str(tmp_path / "pytest.ini"), "--rootdir", str(tmp_path), str(tmp_path)],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


PG_SKIP = 'import pytest\n@pytest.mark.skipif(True, reason="defina TEST_POSTGRES_URL")\ndef test_pg():\n    pass\n\ndef test_ok():\n    pass\n'
PKG_SKIP = 'import pytest\n@pytest.mark.skipif(True, reason="WHATSAPP_DEDUP_PG_ADMIN_URL not set")\ndef test_pg():\n    pass\n'
OTHER_SKIP = 'import pytest\n@pytest.mark.skipif(True, reason="Linux apenas")\ndef test_x():\n    pass\n\ndef test_ok():\n    pass\n'


def test_skip_de_postgres_com_a_guarda_ligada_falha(tmp_path):
    r = _run(tmp_path, PG_SKIP, flag="1")
    assert r.returncode == 1, r.stdout
    assert "testes PostgreSQL pulados" in r.stdout and "test_generated.py::test_pg" in r.stdout


def test_skip_do_pacote_com_a_outra_variavel_tambem_falha(tmp_path):
    assert _run(tmp_path, PKG_SKIP, flag="1").returncode == 1


def test_sem_a_guarda_o_skip_continua_permitido(tmp_path):
    for flag in (None, "0", ""):
        r = _run(tmp_path, PG_SKIP, flag=flag)
        assert r.returncode == 0, (flag, r.stdout)


def test_skip_por_outro_motivo_nao_e_afetado(tmp_path):
    assert _run(tmp_path, OTHER_SKIP, flag="1").returncode == 0


def test_sem_skips_a_guarda_passa(tmp_path):
    assert _run(tmp_path, "def test_a():\n    pass\n", flag="1").returncode == 0


def test_falha_real_continua_sendo_falha(tmp_path):
    assert _run(tmp_path, "def test_a():\n    assert False\n", flag="1").returncode == 1


def test_o_job_do_ci_liga_a_guarda_nos_dois_passos():
    text = (BACKEND.parent / ".github" / "workflows" / "ci.yml").read_text()
    backend_job = text[text.index("  backend:"):text.index("  frontend:")]
    assert '      REQUIRE_POSTGRES_TESTS: "1"' in backend_job
    assert "      TEST_POSTGRES_URL: " in backend_job and "      WHATSAPP_DEDUP_PG_ADMIN_URL: " in backend_job
    pytest_runs = [line.strip() for line in backend_job.splitlines() if line.strip().startswith("run:") and "pytest" in line]
    assert len(pytest_runs) == 2 and all("-p ci_require_postgres" in line for line in pytest_runs), pytest_runs
