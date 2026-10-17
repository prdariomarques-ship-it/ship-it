"""Plano de download do pt-BR: nomes de arquivo lidos do código do Space, revisão curta cabe em 64 caracteres. Sem rede."""
import sys
import textwrap

import pytest

from scripts import download_ptbr_weights as dl


@pytest.fixture
def space(tmp_path):
    pkg = tmp_path / "space" / "chatterbox" / "src" / "chatterbox"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "tts.py").write_text(textwrap.dedent('''
        S3GEN_FILENAME = "s3gen_v3.pt"
        T3_FILENAME = "t3_pt_br.safetensors"
        TOKENIZER_FILENAME = "grapheme_mtl_merged_expanded_v1.json"
    '''), encoding="utf-8")
    saved = {k: v for k, v in sys.modules.items() if k == "chatterbox" or k.startswith("chatterbox.")}
    for k in saved:
        del sys.modules[k]
    yield tmp_path / "space"
    for k in [k for k in sys.modules if k == "chatterbox" or k.startswith("chatterbox.")]:
        del sys.modules[k]
    sys.modules.update(saved)


def test_nomes_vem_do_proprio_space(space):
    assert dl.read_filenames(space) == {
        "tokenizer": "grapheme_mtl_merged_expanded_v1.json", "t3": "t3_pt_br.safetensors", "s3gen": "s3gen_v3.pt"}


def test_space_inexistente(tmp_path):
    with pytest.raises(SystemExit, match="tts.py"):
        dl.read_filenames(tmp_path)


def test_plano_fixa_a_revisao_de_cada_repositorio(space, tmp_path):
    calls = dl.plan(dl.read_filenames(space), str(tmp_path / "w"), "b" * 40, "p" * 40)
    assert [(c["repo_id"], c["revision"]) for c in calls] == [(dl.BASE_REPO_ID, "b" * 40), (dl.PTBR_REPO_ID, "p" * 40)]
    assert calls[0]["allow_patterns"] == ["ve.pt", "grapheme_mtl_merged_expanded_v1.json", "conds.pt"]
    assert calls[1]["allow_patterns"] == ["t3_pt_br.safetensors", "s3gen_v3.pt"]
    assert all(c["local_dir"] == str(tmp_path / "w") for c in calls)


def test_revisao_curta_cabe_na_coluna_do_backend():
    rev = dl.short_revision("a" * 40, "b" * 40)
    assert rev == "base-aaaaaaaaaaaa+ptbr-bbbbbbbbbbbb" and len(rev) <= 64
