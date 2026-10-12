"""API interna do serviço de voz. Sem documentação pública, sem CORS, token obrigatório em todas as rotas de dados."""
from __future__ import annotations

import asyncio
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
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

    # ------------------------------------------------------------------ painel (mesmo serviço: mesmo motor, fila e configuração)
    panel_dir = Path(__file__).parent / "panel"
    panel_csp = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src blob:; "
                 "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    panel_files = {"/panel": ("index.html", "text/html; charset=utf-8"), "/panel/panel.js": ("panel.js", "text/javascript; charset=utf-8"),
                   "/panel/panel.css": ("panel.css", "text/css; charset=utf-8")}

    def _panel_file(path: str):
        name, mime = panel_files[path]
        return FileResponse(panel_dir / name, media_type=mime, headers={"Content-Security-Policy": panel_csp, "Cache-Control": "no-store",
                                                                           "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})

    for _path in panel_files:  # as páginas não contêm dado algum: o token é digitado no navegador e só vale para as rotas /v1
        app.add_api_route(_path, (lambda p=_path: _panel_file(p)), methods=["GET"], include_in_schema=False)

    @app.get("/v1/panel/status")
    async def panel_status(agent: str = Depends(agent_of)):
        simulated = service.engine.name == "fake"
        try:
            profile = service.profile_for(agent)
            profile_info = {"present": True, "display_name": profile.display_name, "consent_authorized": True, "consent_scope": profile.consent_scope,
                            "reference_sha256_prefix": profile.reference_sha256[:12], "has_reference_text": bool(profile.reference_text)}
            profile_error = None
        except SynthError as exc:
            profile_info, profile_error = {"present": False}, exc.message
        real_ready = service.ready and not simulated and bool(profile_info["present"])
        return {
            "agent": agent, "version": __version__, "engine": service.engine.name, "model_id": service.engine.model_id,
            "model_revision": service.engine.model_revision, "ready": service.ready, "not_ready_reason": service.not_ready_reason,
            "mode": "simulado" if simulated else "real",
            # Só é "áudio real com a voz do titular" com motor real carregado E perfil com consentimento. Mesmo assim a aprovação
            # final é humana (escuta das amostras) e não é registrada aqui.
            "real_voice_possible": real_ready,
            "checklist": {
                "motor_real_configurado": not simulated, "pesos_carregados": service.ready and not simulated,
                "perfil_com_consentimento_e_referencia": bool(profile_info["present"]),
                "aprovacao_humana_das_amostras": "pendente (feita fora do sistema)",
            },
            "profile": profile_info, "profile_error": profile_error,
            "queue": {"admitted": service.admitted, "inflight": service.inflight, "max_concurrency": settings.max_concurrency,
                      "queue_max": settings.queue_max, "stored_audios": service.store.count()},
            "limits": {"max_text_chars": settings.max_text_chars, "max_audio_seconds": settings.max_audio_seconds,
                       "result_ttl_seconds": settings.result_ttl_seconds},
            "recent": [r for r in service.recent if r["agent"] == agent][:15],
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
