"""Patch de PRODUCAO (docs/twin-role-inversion/prod): aplicado aos arquivos reais enviados em 24/10 (darius_twin.py sha c9351131..., handlers.py sha ec6dd50c...).

Prova: (1) o patcher aborta se o original nao for o esperado ou se uma ancora nao for unica; (2) o `darius_twin.py` ORIGINAL de producao reproduz o bug
do caso LIBINA (controle negativo, codigo real); (3) o patcheado corrige e preserva o fato do dono; (4) o `handlers.py` patcheado rotula a autoria.
Nenhum LLM real, nenhum envio."""
import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import providers.llm.factory as llm_factory
from models.message import MessageDirection
from providers.llm.base import ChatMessage

PROD = Path(__file__).resolve().parents[2] / "docs" / "twin-role-inversion" / "prod"
BUGGY = "Ainda não, tô na mesma. Febre não baixou ontem à noite, tá ruim de engolir também.\n\nVc tá melhorando aí?"
FIXED = "Ainda não, tô na mesma. Febre não baixou ontem à noite, tá ruim de engolir também."


def _run_patcher(origem: Path, saida: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(PROD / "aplicar_twin_roles.py"), "--origem", str(origem), "--saida", str(saida)],
                          capture_output=True, text=True)


@pytest.fixture(scope="module")
def patched(tmp_path_factory):
    out = tmp_path_factory.mktemp("patched")
    done = _run_patcher(PROD / "originais", out)
    assert done.returncode == 0, done.stderr + done.stdout
    return out


def _load(path: Path, name: str, monkeypatch, reply: str, tmp: Path | None = None):
    async def fake_chat(messages, tools=None):
        fake_chat.calls.append(messages)
        return SimpleNamespace(content=reply)

    fake_chat.calls = []
    monkeypatch.setattr(llm_factory, "chat_with_fallback", fake_chat, raising=False)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompts = (tmp or path.parent) / f"prompts_{name}"
    prompts.mkdir(exist_ok=True)
    (prompts / "darius_twin.md").write_text("PERSONA", encoding="utf-8")
    (prompts / "twin_conversation.md").write_text("CONVERSA", encoding="utf-8")
    module._PROMPT_PATH = prompts / "darius_twin.md"
    module._CONVERSATION_PATH = prompts / "twin_conversation.md"
    return module, fake_chat


# ------------------------------------------------------------------------------------------------------------------------------ patcher
def test_patcher_output_is_pinned_so_the_reviewer_can_compare(patched):
    import hashlib
    assert hashlib.sha256((patched / "darius_twin.py").read_bytes()).hexdigest() == "de076d7314e652eb7b99dea05fd98af5d639ee5d0ed67b62e99653b0fe3c0d0b"
    assert hashlib.sha256((patched / "handlers.py").read_bytes()).hexdigest() == "c47650be7bc4e60f59b8a54e13aaf2d6447d38db8d9f60bff6261a664ca54f7c"


def test_patcher_aborts_on_an_unexpected_original_and_writes_nothing(tmp_path):
    origem = tmp_path / "o"
    origem.mkdir()
    (origem / "handlers.py").write_bytes((PROD / "originais" / "handlers.py").read_bytes())
    (origem / "darius_twin.py").write_text((PROD / "originais" / "darius_twin.py").read_text() + "\n# alterado\n")
    done = _run_patcher(origem, tmp_path / "saida")
    assert done.returncode != 0 and "nao e o original esperado" in done.stderr
    assert not (tmp_path / "saida").exists()


def test_patcher_aborts_when_an_anchor_is_not_unique(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("patcher", PROD / "aplicar_twin_roles.py")
    patcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patcher)
    text = (PROD / "originais" / "handlers.py").read_text()
    anchor = patcher.HANDLERS_EDITS[0][1]
    with pytest.raises(SystemExit):
        patcher.apply("handlers.py", text + anchor, patcher.HANDLERS_EDITS)           # ancora duplicada
    with pytest.raises(SystemExit):
        patcher.apply("handlers.py", text.replace(anchor, ""), patcher.HANDLERS_EDITS)  # ancora ausente


# --------------------------------------------------------------------------------------------- codigo real: antes (bug) e depois (corrigido)
async def test_NEGATIVE_CONTROL_the_original_production_twin_reproduces_the_libina_bug(monkeypatch, tmp_path):
    original, _ = _load(PROD / "originais" / "darius_twin.py", "twin_original", monkeypatch, BUGGY, tmp_path)
    history = [ChatMessage(role="user", content="Oi Netinho"), ChatMessage(role="user", content="Melhorou?")]
    assert await original.generate_darius_reply(history, "Como vc está?", contact_name="Gerente LIBINA") == BUGGY


async def test_patched_production_twin_drops_the_returned_question_and_keeps_the_owners_state(patched, monkeypatch):
    twin, fake = _load(patched / "darius_twin.py", "twin_patched", monkeypatch, BUGGY)
    history = [ChatMessage(role="user", content="Oi Netinho"), ChatMessage(role="user", content="Melhorou?")]
    assert await twin.generate_darius_reply(history, "Como vc está?", contact_name="Gerente LIBINA") == FIXED
    systems = [m.content for m in fake.calls[0] if m.role == "system"]
    assert systems[0].startswith("PERSONA\n\nCONVERSA") and "SOBRE O DÁRIO" in systems[0]
    assert systems[1].startswith("Você está respondendo, pelo WhatsApp, para: Gerente LIBINA.") and "NÃO é o Dário" in systems[1]


async def test_patched_production_twin_controls_sick_contact_and_nicknames(patched, monkeypatch):
    twin, _ = _load(patched / "darius_twin.py", "twin_patched2", monkeypatch, BUGGY)
    sick = [ChatMessage(role="user", content="Tô gripado desde segunda")]
    assert await twin.generate_darius_reply(sick, "E você, melhorou?", contact_name="Paulo") == BUGGY          # contato doente: pergunta volta
    twin2, _ = _load(patched / "darius_twin.py", "twin_patched3", monkeypatch, "Entendi, Adriane. Obrigado por avisar.")
    history = [ChatMessage(role="user", content="Oi, pastor Adriane, tudo bem, graças a Deus.")]
    assert await twin2.generate_darius_reply(history, "Vou sair da igreja", contact_name="Gerente LIBINA") == "Entendi. Obrigado por avisar."
    twin3, _ = _load(patched / "darius_twin.py", "twin_patched4", monkeypatch, "Oi, Maria! Tudo bem?")
    assert await twin3.generate_darius_reply([], "Oi Maria", contact_name="Maria Silva") == "Oi, Maria! Tudo bem?"   # nome do contato preservado


async def test_patched_production_twin_kill_switch_by_environment(patched, monkeypatch):
    monkeypatch.setenv("TWIN_ROLE_GUARD_ENABLED", "false")
    twin, _ = _load(patched / "darius_twin.py", "twin_patched5", monkeypatch, BUGGY)
    assert await twin.generate_darius_reply([], "Como vc está?", contact_name="X") == BUGGY


async def test_patched_production_twin_empty_after_guard_is_unavailable_never_inverted(patched, monkeypatch):
    twin, _ = _load(patched / "darius_twin.py", "twin_patched6", monkeypatch, "E você, melhorou?")
    with pytest.raises(twin.TwinReplyUnavailable):
        await twin.generate_darius_reply([], "Melhorou?", contact_name="X")


# ------------------------------------------------------------------------------------------------------------------ handlers de producao
def test_patched_production_handler_labels_authorship_with_the_real_history_line(patched):
    source = (patched / "handlers.py").read_text()
    ast.parse(source)
    assert "from agents.darius_twin_roles import build_twin_history" in source
    line = re.search(r"^\s+chat_history = build_twin_history\(.*\)$", source, re.M).group(0).strip()
    assert "twin_history_content(m, _owner_audio_history_content(m))" in line and "exclude_id=message_id" in line
    from agents.darius_twin_roles import build_twin_history
    rows = [
        SimpleNamespace(id=1, direction=MessageDirection.INBOUND, content="Bom dia", sent_by_human=False, is_autopilot_reply=False),
        SimpleNamespace(id=2, direction=MessageDirection.OUTBOUND, content="Bom dia, tudo certo?", sent_by_human=True, is_autopilot_reply=False),
        SimpleNamespace(id=3, direction=MessageDirection.OUTBOUND, content="Vou ver isso.", sent_by_human=False, is_autopilot_reply=True),
        SimpleNamespace(id=4, direction=MessageDirection.INBOUND, content="Melhorou?", sent_by_human=False, is_autopilot_reply=False),
    ]
    ns = {"build_twin_history": build_twin_history, "history": rows, "message_id": 4, "twin_history_content": lambda m, c: c,
          "_owner_audio_history_content": lambda m: m.content}
    exec(line, ns)
    assert [(m.role, m.content) for m in ns["chat_history"]] == [("user", "Bom dia"), ("assistant", "[Dário] Bom dia, tudo certo?"), ("assistant", "[Gêmeo] Vou ver isso.")]


def test_the_handler_diff_is_limited_to_the_three_documented_edits(patched):
    import difflib
    old = (PROD / "originais" / "handlers.py").read_text().splitlines()
    new = (patched / "handlers.py").read_text().splitlines()
    removed = [row for row in difflib.unified_diff(old, new, lineterm="", n=0) if row[:1] == "-" and row[:3] != "---"]
    assert len(removed) == 1 and "chat_history = [ChatMessage(" in removed[0], removed       # so a linha do historico sai; o resto e acrescimo
