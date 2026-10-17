"""Cliente HTTP somente-leitura do Dario OS.

Mesma política de resiliência do shim FlowCore (`agents/tools/flowcore_tools.py`):
backoff exponencial em erro de transporte e 5xx; 4xx não se repete. Aqui só
existe GET, de propósito: o token tem escopo de leitura e a ponte não deve ter
um caminho de código capaz de escrever.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class DarioOSError(Exception):
    """Falha ao consultar o Dario OS (mensagem segura para repassar ao modelo)."""


class DarioOSClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 15.0,
        max_attempts: int = 3,
        backoff: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._max_attempts = max_attempts
        self._backoff = backoff
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        last: str = "sem resposta"
        for attempt in range(self._max_attempts):
            try:
                response = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                last = f"erro de transporte ({type(exc).__name__})"
            else:
                if response.status_code == 200:
                    return response.json()
                last = f"HTTP {response.status_code}"
                if response.status_code < 500:
                    # 401/403: token expirado, revogado ou fora do escopo; 404/422:
                    # pedido inválido. Repetir não muda nada.
                    raise DarioOSError(f"Dario OS recusou o pedido ({last})")
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff * (2**attempt))
        raise DarioOSError(f"Dario OS indisponível ({last})")
