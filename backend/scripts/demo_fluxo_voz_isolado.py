#!/usr/bin/env python3
"""Demonstração do fluxo em ambiente ISOLADO: resposta comercial -> texto -> voz -> serviço de voz (HTTP real) -> OGG/Opus
validado -> fila -> transporte WhatsApp SIMULADO. Banco SQLite temporário, dados fictícios, nenhuma mensagem real.

O serviço de voz precisa estar de pé (ex.: voice-service com VOICE_ENGINE=fake, que gera um SINAL DE TESTE, não fala nem voz
alguma; com os pesos reais e a referência autorizada o mesmo roteiro gera a voz do perfil).

  VOICE_URL=http://127.0.0.1:18765 VOICE_TOKEN=<token do agente loja> python scripts/demo_fluxo_voz_isolado.py [--save-audio DIR]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _env(url: str, token: str, db: Path) -> None:
    os.environ.update({
        "DATABASE_URL": f"sqlite+aiosqlite:///{db}", "ENVIRONMENT": "test", "JWT_SECRET": "demo-secret-key-with-enough-bytes-for-hs256",
        "STORE_WHATSAPP_ENABLED": "true", "AUTO_REPLY_ENABLED": "true", "EVOLUTION_INSTANCE": "MARQUESCOLOR",
        "EVOLUTION_PERSONAL_INSTANCE": "pessoal-demo", "STORE_VOICE_ENABLED": "true", "STORE_VOICE_URL": url, "STORE_VOICE_TOKEN": token,
        "JOBS_RETRY_BACKOFF_SECONDS": "0", "WHATSAPP_REQUEST_MAX_ATTEMPTS": "1",
    })


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"não foi possível carregar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--save-audio", type=Path, default=None)
    args = ap.parse_args(argv)
    url, token = os.environ.get("VOICE_URL", ""), os.environ.get("VOICE_TOKEN", "")
    if not url or not token:
        print("defina VOICE_URL e VOICE_TOKEN no ambiente", file=sys.stderr)
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="demo-voz-"))
    _env(url, token, tmp / "demo.db")

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import jobs.handlers  # noqa: F401
    import jobs.worker as worker_mod
    import models  # noqa: F401
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from database.base import Base
    from jobs.service import JobService
    from models.contact import Contact
    from models.message import Message, MessageDirection, MessageMediaType
    from models.store_voice import StoreVoiceSend
    from services import store_voice
    from services.ogg_opus import inspect_ogg_opus

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def control(sync_conn):
            mods = [_load(f"m{i}", ROOT / "alembic" / "versions" / n) for i, n in enumerate(("e610080001_pause_control.py", "e610080002_review_delivery.py"))]
            with Operations.context(MigrationContext.configure(sync_conn)):
                for m in mods:
                    m.upgrade()
        await conn.run_sync(control)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    worker_mod.async_session_factory = sessions

    sent_text: list[dict] = []
    sent_voice: list[dict] = []

    class TextTransport:
        name, default_instance = "evolution", "MARQUESCOLOR"

        async def send_text(self, to, content, instance=None):
            sent_text.append({"to": to, "content": content})
            return {"key": {"id": f"DEMO-TXT-{len(sent_text)}"}}

    class VoiceTransport:
        name, default_instance = "evolution", "MARQUESCOLOR"

        async def send_voice(self, to, audio_base64, instance=None):
            sent_voice.append({"to": to, "instance": instance, "audio": base64.b64decode(audio_base64)})
            return {"key": {"id": f"DEMO-VOZ-{len(sent_voice)}"}}

    jobs.handlers.get_whatsapp_provider = lambda: TextTransport()  # type: ignore[assignment]  # transporte simulado da demonstração
    store_voice.get_whatsapp_provider = lambda: VoiceTransport()  # type: ignore[assignment]

    reply = "Temos sim a tinta que você pediu.\nItens:\n- 2 x Tinta Látex Branca 18L\nO valor e as condições seguem por escrito."
    async with sessions() as db:
        contact = Contact(name="Cliente Fictício", phone="5511999990000", preferences={})
        db.add(contact)
        await db.flush()
        msg = Message(contact_id=contact.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.AUDIO, content="[áudio] preciso de tinta",
                      whatsapp_instance="MARQUESCOLOR")
        db.add(msg)
        await db.commit()
        await JobService(db).enqueue("whatsapp.send_text", {"to": contact.phone, "content": reply, "instance": "MARQUESCOLOR",
                                                            "voice_companion": {"source_message_id": msg.id}})
    for _ in range(8):
        if not await worker_mod.JobWorker().run_once():
            break
    async with sessions() as db:
        rows = (await db.scalars(select(StoreVoiceSend))).all()
    trace = {
        "texto_enviado_primeiro": sent_text,
        "voz": [{"destino": v["to"], "instancia": v["instance"], "bytes": len(v["audio"]),
                 "ogg_opus_mono_valido": bool(inspect_ogg_opus(v["audio"], max_bytes=4_000_000, max_seconds=40.0)),
                 "duracao_s": round(inspect_ogg_opus(v["audio"], max_bytes=4_000_000, max_seconds=40.0).duration_seconds, 2)} for v in sent_voice],
        "linhas_store_voice_sends": [{"id": r.id, "status": r.status, "roteiro": r.script_text, "motor": r.engine, "recibo": r.receipt_id,
                                      "historico": [h["event"] for h in r.history]} for r in rows],
    }
    if args.save_audio and sent_voice:
        args.save_audio.mkdir(parents=True, exist_ok=True, mode=0o700)
        (args.save_audio / "demo_fluxo.ogg").write_bytes(sent_voice[0]["audio"])
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    await engine.dispose()
    return 0 if rows and rows[0].status == "sent" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
