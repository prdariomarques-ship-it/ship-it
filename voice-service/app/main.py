"""API interna do serviço de voz. Sem documentação pública, sem CORS, token obrigatório em todas as rotas de dados."""
from __future__ import annotations

import asyncio
import hmac
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app import __version__
from app.config import VoiceSettings, get_settings
from app.engines.base import Engine, build_engine
from app.service import SynthError, SynthService
from app.storage import AudioStore

MIME = "audio/ogg; codecs=opus"


class SynthesizeIn(BaseModel):
    request_id: str = Field(min_length=8, max_length=64)
    text: str = Field(max_length=4000)  # limite real (max_text_chars) é do serviço; este só protege o parser
    language: str = "pt"


def create_app(settings: VoiceSettings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    tokens = settings.token_map()  # levanta se não houver autenticação válida
    store = AudioStore(settings.storage_dir, settings.result_ttl_seconds)
    service = SynthService(settings, engine or build_engine(settings), store)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(service.load_engine)

        async def _janitor() -> None:
            while True:
                await asyncio.sleep(settings.cleanup_interval_seconds)
                service.sweep()

        task = asyncio.create_task(_janitor())
        try:
            yield
        finally:
            task.cancel()
            service.shutdown()

    app = FastAPI(title="voice-service", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = service

    def agent_of(authorization: str | None = Header(default=None)) -> str:
        scheme, _, supplied = (authorization or "").partition(" ")
        agent = None
        if scheme.lower() == "bearer" and supplied:
            for token, name in tokens.items():  # percorre todos: tempo independente de qual casa
                if hmac.compare_digest(token.encode(), supplied.encode()):
                    agent = name
        if agent is None:
            raise HTTPException(status_code=401, detail="não autorizado", headers={"WWW-Authenticate": "Bearer"})
        return agent

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > settings.max_request_body_bytes:
            return JSONResponse({"error": {"code": "body_too_large", "message": "corpo acima do limite"}}, status_code=413)
        return await call_next(request)

    @app.exception_handler(SynthError)
    async def synth_error(_request: Request, exc: SynthError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse({"error": {"code": "http_%d" % exc.status_code, "message": str(exc.detail)}},
                            status_code=exc.status_code, headers=exc.headers)

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(agent: str = Depends(agent_of)):
        profiles = []
        for sub in sorted(p.name for p in settings.profiles_dir.glob("*") if p.is_dir()) if settings.profiles_dir.exists() else []:
            try:
                service.profile_for(sub)
                profiles.append(sub)
            except SynthError:
                continue
        return {
            "ready": service.ready, "reason": service.not_ready_reason, "engine": service.engine.name,
            "model_id": service.engine.model_id, "model_revision": service.engine.model_revision,
            "profiles": profiles if agent in profiles else [], "admitted": service.admitted, "inflight": service.inflight,
            "max_concurrency": settings.max_concurrency, "queue_max": settings.queue_max, "version": __version__,
        }

    @app.post("/v1/synthesize")
    async def synthesize(body: SynthesizeIn, agent: str = Depends(agent_of)):
        stored = await service.synthesize(agent, body.request_id, body.text, body.language)
        profile = service.profile_for(agent)
        return {
            "audio_id": stored.audio_id, "mime": MIME, "duration_seconds": round(stored.duration_seconds, 3),
            "size_bytes": stored.size, "sha256": stored.sha256, "expires_in_seconds": settings.result_ttl_seconds,
            "engine": service.engine.name, "model_revision": service.engine.model_revision,
            "profile": profile.agent, "reference_sha256": profile.reference_sha256, "synthetic_voice": True,
        }

    @app.get("/v1/audio/{audio_id}")
    async def get_audio(audio_id: str, agent: str = Depends(agent_of)):
        item = service.store.get(audio_id, agent)
        if item is None:
            raise HTTPException(status_code=404, detail="áudio inexistente ou expirado")
        return Response(content=item.path.read_bytes(), media_type=MIME,
                        headers={"X-Audio-SHA256": item.sha256, "Cache-Control": "no-store"})

    @app.delete("/v1/audio/{audio_id}", status_code=204)
    async def delete_audio(audio_id: str, agent: str = Depends(agent_of)):
        if not service.store.delete(audio_id, agent):
            raise HTTPException(status_code=404, detail="áudio inexistente")
        return Response(status_code=204)

    return app
