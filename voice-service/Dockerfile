# Serviço de voz — imagem NÃO construída neste repositório (sem Docker no ambiente de desenvolvimento).
# Fixe o digest da imagem base no build (python:3.11.15-slim@sha256:<preencher>) antes de qualquer uso real.
FROM python:3.11.15-slim
ARG ENGINE=chatterbox
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 \
    VOICE_HOST=0.0.0.0 VOICE_PORT=8765 \
    VOICE_STORAGE_DIR=/var/lib/voice-service/tmp VOICE_PROFILES_DIR=/var/lib/voice-service/profiles VOICE_MODEL_DIR=/models
WORKDIR /srv
COPY requirements.txt requirements-chatterbox.txt requirements-qwen3tts.txt ./
RUN pip install --no-cache-dir -r requirements-${ENGINE}.txt
COPY app ./app
RUN useradd --system --uid 10001 voice && mkdir -p /var/lib/voice-service/tmp && chown -R voice /var/lib/voice-service
USER voice
# 0.0.0.0 só dentro do contêiner; a publicação de porta fica a cargo do compose (rede interna, sem ports:).
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/healthz',timeout=3)"
CMD ["python", "-m", "uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8765", "--no-server-header"]
