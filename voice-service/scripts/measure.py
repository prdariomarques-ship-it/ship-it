"""Mede o motor configurado NO HARDWARE ONDE RODA: tempo por amostra, duração do áudio, fator tempo-real, pico de RAM,
pico de VRAM (se houver GPU) e comportamento sob concorrência. Escreve JSON; não inventa números.

O hardware medido é descrito no próprio relatório (CPU, núcleos, RAM total, GPU). Quem lê o relatório deve ler essa seção
antes dos números. Uso (dentro do ambiente do motor): VOICE_ENGINE=... python -m scripts.measure --agent loja --repeat 3
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import psutil

from app import audio
from app.config import VoiceSettings
from app.engines.base import build_engine
from app.profiles import load_profile

# Textos FICTÍCIOS (nenhum cliente, preço ou pedido reais).
from scripts.samples import SAMPLES  # noqa: E402,F401  (reexportado: make_samples e testes importam daqui)


def hardware() -> dict:
    gpu = None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            gpu = out.stdout.strip().splitlines()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"cpu": platform.processor() or platform.machine(), "cores_logical": psutil.cpu_count(), "ram_total_gb": round(psutil.virtual_memory().total / 2**30, 1),
            "gpu": gpu, "python": platform.python_version(), "os": platform.platform()}


class PeakRss:
    def __init__(self, interval: float = 0.05) -> None:
        self.proc, self.peak, self._stop, self.interval = psutil.Process(), 0, threading.Event(), interval
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, self.proc.memory_info().rss)
            time.sleep(self.interval)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        self.peak = max(self.peak, self.proc.memory_info().rss)


def vram_peak_mb() -> float | None:
    try:
        import torch
        if torch.cuda.is_available():
            return round(torch.cuda.max_memory_allocated() / 2**20, 1)
    except Exception:  # noqa: BLE001
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent", default="loja")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=2, help="threads simultâneas no teste de concorrência")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    s = VoiceSettings(tokens="x=" + "x" * 40, allow_fake_engine=os.environ.get("VOICE_ALLOW_FAKE_ENGINE", "") == "true")
    profile = load_profile(s.profiles_dir, args.agent)
    engine = build_engine(s)
    report: dict = {"hardware": hardware(), "engine": engine.name, "model_id": engine.model_id, "model_revision": s.model_revision,
                    "device": s.device, "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "samples": {}}
    with PeakRss() as rss:
        t0 = time.perf_counter()
        engine.load()
        report["load_seconds"] = round(time.perf_counter() - t0, 2)
        for name, text in SAMPLES.items():
            runs = []
            for _ in range(args.repeat):
                t = time.perf_counter()
                res = engine.synthesize(text, profile.language, profile.reference_path, profile.reference_text)
                gen = time.perf_counter() - t
                secs = len(res.samples) / res.sample_rate
                data = audio.encode_ogg_opus(res.samples, res.sample_rate, s.opus_bitrate, s.target_peak_dbfs)
                audio.probe_ogg_opus(data)
                runs.append({"generation_seconds": round(gen, 2), "audio_seconds": round(secs, 2), "real_time_factor": round(gen / secs, 2)})
            report["samples"][name] = {"chars": len(text), "runs": runs,
                                       "generation_seconds_median": round(statistics.median(r["generation_seconds"] for r in runs), 2)}
        lock = threading.Lock()  # o serviço serializa o motor; aqui mede o custo da fila com N chamadores
        text = SAMPLES["retomada_orcamento"]
        started = time.perf_counter()

        def one(_):
            t = time.perf_counter()
            with lock:
                engine.synthesize(text, profile.language, profile.reference_path, profile.reference_text)
            return time.perf_counter() - t

        with ThreadPoolExecutor(args.concurrency) as pool:
            lat = list(pool.map(one, range(args.concurrency)))
        report["concurrency"] = {"callers": args.concurrency, "wall_seconds": round(time.perf_counter() - started, 2),
                                 "latencies_seconds": [round(v, 2) for v in lat]}
    report["peak_rss_mb"] = round(rss.peak / 2**20, 1)
    report["peak_vram_mb"] = vram_peak_mb()
    text_out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text_out)
    print(text_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
