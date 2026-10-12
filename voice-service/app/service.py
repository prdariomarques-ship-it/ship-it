"""Orquestração da síntese: validação, idempotência por request_id, fila limitada, timeout e armazenamento.

Regras:
- no máximo `max_concurrency` sínteses em andamento; até `queue_max` esperando; além disso -> Busy (HTTP 429);
- o contador de admitidos só cai quando o THREAD do motor termina (um timeout não libera capacidade que ainda está em uso);
- o mesmo (agente, request_id) nunca gera duas vezes: reaproveita o resultado em andamento ou já pronto.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from app import audio as audio_mod
from app.engines.base import Engine, EngineError, EngineNotReady
from app.profiles import ProfileError, VoiceProfile, load_profile
from app.storage import AudioStore, StoredAudio

_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SynthError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class SynthService:
    def __init__(self, settings, engine: Engine, store: AudioStore) -> None:
        self.s = settings
        self.engine = engine
        self.store = store
        self.ready = False
        self.not_ready_reason = "motor ainda não carregado"
        self._executor = ThreadPoolExecutor(max_workers=settings.max_concurrency, thread_name_prefix="tts")
        self._engine_lock = threading.Lock()
        self._admitted = 0
        self._inflight: dict[tuple[str, str], asyncio.Future] = {}
        self._done: dict[tuple[str, str], tuple[StoredAudio, float]] = {}
        self._profiles: dict[str, tuple[VoiceProfile, float]] = {}
        # Histórico curto para o painel (só metadados: nunca o texto nem o áudio). Mesmo serviço, mesma fila, mesma configuração.
        self.recent: deque[dict] = deque(maxlen=30)

    # ------------------------------------------------------------------ ciclo de vida
    def load_engine(self) -> None:
        try:
            self.engine.load()
            self.ready, self.not_ready_reason = True, ""
        except EngineNotReady as exc:
            self.ready, self.not_ready_reason = False, str(exc)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def admitted(self) -> int:
        return self._admitted

    @property
    def inflight(self) -> int:
        return len(self._inflight)

    # ------------------------------------------------------------------ perfis
    def profile_for(self, agent: str) -> VoiceProfile:
        meta = self.s.profiles_dir / agent / "profile.json"
        try:
            mtime = meta.stat().st_mtime
        except OSError:
            mtime = -1.0
        cached = self._profiles.get(agent)
        if cached and cached[1] == mtime:
            return cached[0]
        try:
            profile = load_profile(self.s.profiles_dir, agent)
        except ProfileError as exc:
            raise SynthError(404, "profile_unavailable", str(exc)) from exc
        self._profiles[agent] = (profile, mtime)
        return profile

    # ------------------------------------------------------------------ validação
    def _validate(self, request_id: str, text: str, language: str) -> str:
        if not _REQUEST_ID.match(request_id or ""):
            raise SynthError(400, "invalid_request_id", "request_id: 8 a 64 caracteres [A-Za-z0-9_.:-]")
        cleaned = _CONTROL.sub(" ", text or "").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            raise SynthError(400, "empty_text", "texto vazio")
        if len(cleaned) > self.s.max_text_chars:
            raise SynthError(413, "text_too_long", f"texto acima de {self.s.max_text_chars} caracteres")
        if language != "pt":
            raise SynthError(400, "unsupported_language", "somente 'pt' (português do Brasil) nesta versão")
        return cleaned

    # ------------------------------------------------------------------ síntese
    def _run(self, text: str, profile: VoiceProfile) -> tuple[bytes, audio_mod.AudioInfo]:
        with self._engine_lock:  # motores não são thread-safe
            started = time.perf_counter()
            result = self.engine.synthesize(text, profile.language, profile.reference_path, profile.reference_text)
            self.last_generation_seconds = time.perf_counter() - started
        seconds = len(result.samples) / float(result.sample_rate) if result.sample_rate else 0.0
        if seconds < self.s.min_audio_seconds:
            raise SynthError(422, "audio_too_short", "áudio gerado vazio ou curto demais")
        if seconds > self.s.max_audio_seconds:
            raise SynthError(422, "audio_too_long", f"áudio gerado acima de {self.s.max_audio_seconds:.0f} s")
        try:
            data = audio_mod.encode_ogg_opus(result.samples, result.sample_rate, self.s.opus_bitrate, self.s.target_peak_dbfs)
            info = audio_mod.probe_ogg_opus(data)
        except audio_mod.AudioFormatError as exc:
            raise SynthError(502, "invalid_audio_format", str(exc)) from exc
        return data, info

    def _record(self, agent: str, request_id: str, status: str, started: float, chars: int) -> None:
        self.recent.appendleft({"at": time.time(), "agent": agent, "request_id": request_id, "status": status,
                                "seconds": round(time.time() - started, 2), "chars": chars})

    async def synthesize(self, agent: str, request_id: str, text: str, language: str) -> StoredAudio:
        started, chars = time.time(), len(text or "")
        try:
            stored = await self._synthesize(agent, request_id, text, language)
        except SynthError as exc:
            self._record(agent, request_id, exc.code, started, chars)
            raise
        self._record(agent, request_id, "ok", started, chars)
        return stored

    async def _synthesize(self, agent: str, request_id: str, text: str, language: str) -> StoredAudio:
        text = self._validate(request_id, text, language)
        if not self.ready:
            raise SynthError(503, "engine_not_ready", self.not_ready_reason or "motor indisponível")
        profile = self.profile_for(agent)
        key = (agent, request_id)

        done = self._done.get(key)
        if done is not None:
            audio, expires = done
            if time.time() < expires and self.store.get(audio.audio_id, agent) is not None:
                return audio
            self._done.pop(key, None)

        fut = self._inflight.get(key)
        if fut is None:
            if self._admitted >= self.s.max_concurrency + self.s.queue_max:
                raise SynthError(429, "busy", "fila de síntese cheia; tente novamente depois")
            loop = asyncio.get_running_loop()
            self._admitted += 1
            fut = loop.run_in_executor(self._executor, self._run, text, profile)
            self._inflight[key] = fut

            def _finished(f: asyncio.Future, key=key, agent=agent) -> None:
                self._admitted -= 1
                self._inflight.pop(key, None)
                if f.cancelled() or f.exception() is not None:
                    return
                data, info = f.result()
                stored = self.store.put(agent, data, hashlib.sha256(data).hexdigest(), info.duration_seconds)
                self._done[key] = (stored, time.time() + self.s.result_ttl_seconds)

            fut.add_done_callback(_finished)
        try:
            data_info = await asyncio.wait_for(asyncio.shield(fut), timeout=self.s.generation_timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise SynthError(504, "generation_timeout", "tempo de geração excedido") from exc
        except SynthError:
            raise
        except EngineNotReady as exc:
            raise SynthError(503, "engine_not_ready", str(exc)) from exc
        except EngineError as exc:
            raise SynthError(500, "engine_failure", str(exc)[:200]) from exc
        _ = data_info
        done = self._done.get(key)
        if done is None:  # callback ainda não rodou (corrida mínima): processa de forma determinística
            await asyncio.sleep(0)
            done = self._done.get(key)
        if done is None:
            raise SynthError(500, "result_lost", "resultado indisponível")
        return done[0]

    def sweep(self) -> int:
        now = time.time()
        for key in [k for k, (_, exp) in self._done.items() if now >= exp]:
            self._done.pop(key, None)
        return self.store.sweep(now)
