FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY zervis_bridge ./zervis_bridge

RUN useradd --system --no-create-home bridge
USER bridge

EXPOSE 8810

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8810/healthz', timeout=4)"

CMD ["python", "-m", "zervis_bridge"]
