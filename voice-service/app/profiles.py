"""Perfis de voz, um por agente. Um perfil só existe com consentimento registrado e referência íntegra (SHA-256)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class VoiceProfile:
    agent: str
    display_name: str
    language: str
    reference_path: Path
    reference_sha256: str
    reference_text: str | None
    consent_owner: str
    consent_scope: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_profile(profiles_dir: Path, agent: str) -> VoiceProfile:
    if not _NAME.match(agent or ""):
        raise ProfileError("nome de perfil inválido")
    base = (Path(profiles_dir) / agent).resolve()
    if Path(profiles_dir).resolve() not in base.parents:
        raise ProfileError("perfil fora do diretório de perfis")
    meta_path = base / "profile.json"
    if not meta_path.is_file():
        raise ProfileError(f"perfil {agent!r} inexistente")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError("profile.json ilegível") from exc
    if meta.get("agent") != agent:
        raise ProfileError("o campo 'agent' do perfil não confere com o diretório")
    consent = meta.get("consent") or {}
    if consent.get("authorized") is not True or not consent.get("voice_owner") or not consent.get("scope"):
        raise ProfileError("perfil sem consentimento registrado (authorized/voice_owner/scope)")
    ref = (base / str(meta.get("reference_file", ""))).resolve()
    if base not in ref.parents or not ref.is_file():
        raise ProfileError("arquivo de referência ausente ou fora do perfil")
    digest = _sha256(ref)
    if digest != meta.get("reference_sha256"):
        raise ProfileError("SHA-256 da referência não confere com o perfil")
    language = str(meta.get("language", "pt"))
    return VoiceProfile(
        agent=agent, display_name=str(meta.get("display_name", agent)), language=language, reference_path=ref,
        reference_sha256=digest, reference_text=(meta.get("reference_text") or None),
        consent_owner=str(consent["voice_owner"]), consent_scope=str(consent["scope"]),
    )
