"""Seeds an ISOLATED Dario OS SQLite file (path comes from DATABASE_URL, must live under e2e/run)."""
from __future__ import annotations

import asyncio
import os
import sys

URL = os.environ["DATABASE_URL"]
if not URL.startswith("postgresql+asyncpg://postgres:c6tmp@127.0.0.1:15432/c6"):
    raise SystemExit(f"refusing to seed a non-isolated database: {URL.split('@')[-1]}")

sys.path.insert(0, r"C:\Users\dario\FlowCore\ship-it\backend")

import main  # noqa: E402,F401  -- registers every model on Base.metadata
from auth.password import hash_password  # noqa: E402
from database.base import Base  # noqa: E402
from database.session import async_session_factory, engine  # noqa: E402
from models.contact import Contact  # noqa: E402
from models.darius_whatsapp_task import DariusWhatsAppTask  # noqa: E402
from models.message import Message, MessageDirection, MessageMediaType  # noqa: E402
from models.user import User, UserRole  # noqa: E402
from services import conversation_control  # noqa: E402
from tests.test_darius_whatsapp import _migrate_control_tables_sync  # noqa: E402


async def run() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_control_tables_sync)
    async with async_session_factory() as db:
        admin = User(email="admin@example.com", full_name="Admin E2E", hashed_password=hash_password("e2e-admin-pass-1"),
                     role=UserRole.ADMIN, is_active=True)
        member = User(email="user@example.com", full_name="Usuario E2E", hashed_password=hash_password("e2e-user-pass-1"),
                      role=UserRole.USER, is_active=True)
        db.add_all([admin, member])
        contacts = [Contact(name=n, phone=p, preferences={}) for n, p in
                    [("Ana Souza", "5511999990001"), ("Bruno Lima", "5511999990002"), ("Carla Dias", "5511999990003")]]
        db.add_all(contacts)
        await db.flush()
        await conversation_control.pause(db, contacts[0].id, "store", "e2e-pause-1", "dono assumiu a conversa", admin.id)
        await conversation_control.pause(db, contacts[1].id, "personal", "e2e-pause-2", "cliente pediu atendimento humano", None)
        for i, (status, dstatus, err) in enumerate([
            ("reply_queued", "COMPLETED", None), ("failed", "FAILED", "Exceeded maximum iterations"),
            ("expired", "RUNNING", None), ("submitted", "RUNNING", None),
        ]):
            message = Message(contact_id=contacts[2].id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT,
                              content="(conteudo de teste e2e)", whatsapp_instance="store", external_id=f"E2E-{i}")
            db.add(message)
            await db.flush()
            db.add(DariusWhatsAppTask(dedupe_key=f"e2e-{i:02d}", message_id=message.id, contact_id=contacts[2].id,
                                      instance="store", status=status, darius_task_id=f"e2e-task-{i}",
                                      darius_status=dstatus, attempts=i + 1, last_error=err, history=[]))
        await db.commit()
    print("seeded dario os:", URL.rsplit("/", 1)[-1])


asyncio.run(run())
