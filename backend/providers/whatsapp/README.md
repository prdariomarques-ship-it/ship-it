# Como desenvolver um novo Provider de WhatsApp

Esta é a única porta de entrada para integrar um novo gateway de WhatsApp (Baileys,
Evolution API, WhatsApp Business Cloud API, ou qualquer outro) ao Dario OS.
Nenhuma outra camada da aplicação — Agent Registry, Tool Registry, Event Bus,
Memory Manager, AI Orchestrator, rotas, jobs — precisa mudar. Trocar de
provider é configuração (`WHATSAPP_PROVIDER=<nome>`), nunca código de negócio.

## O contrato

Todo Provider implementa `WhatsAppProvider` (`providers/whatsapp/base.py`):

```python
class WhatsAppProvider(ABC):
    name: str  # identificador único; é o valor de WHATSAPP_PROVIDER que seleciona este provider

    # --- Envio: obrigatórios ---
    async def send_text(self, to: str, content: str) -> dict: ...
    async def send_image(self, to: str, url: str, filename: str = "image", caption: str = "") -> dict: ...
    async def send_file(self, to: str, url: str, filename: str = "file", caption: str = "") -> dict: ...
    async def send_audio(self, to: str, url: str) -> dict: ...
    async def send_location(self, to: str, latitude: float, longitude: float, caption: str = "") -> dict: ...

    # --- Recebimento: obrigatório ---
    def parse_webhook(self, payload: dict) -> InboundMessage | None: ...

    # --- Recebimento: opcionais (default = "este provider não relata isso") ---
    def parse_connection_event(self, payload: dict) -> ConnectionEvent | None: ...
    def parse_delivery_ack(self, payload: dict) -> DeliveryAck | None: ...

    # --- Operacional: opcionais ---
    async def health_check(self) -> bool: ...              # default: True
    def verify_signature(self, raw_body: bytes, headers) -> bool: ...  # default: True (no-op)
```

### Regra de ouro: só tradução e transporte

Um Provider **nunca** acessa o banco, nunca enfileira jobs, nunca publica no
Event Bus, nunca conhece regra de negócio. Ele só faz duas coisas:

1. **Enviar** — traduzir uma chamada genérica (`send_text(to, content)`) para a
   API específica do gateway.
2. **Traduzir eventos** — normalizar o payload cru do webhook do gateway para
   um dos três modelos internos únicos (`InboundMessage`, `ConnectionEvent`,
   `DeliveryAck`). Depois dessa tradução, **nenhum outro componente do sistema
   sabe ou precisa saber qual gateway está configurado** — o restante da
   aplicação (webhook route, jobs, agentes) só conhece esses três modelos.

Quem decide o que *fazer* com um evento traduzido é `webhooks/router.py`, não
o Provider.

## Modelos internos (o "formato único")

```python
class InboundMessage(BaseModel):
    phone: str
    text: str = ""
    sender_name: str = ""
    external_id: str = ""
    media_type: str = "text"
    timestamp: datetime | None = None  # hora do evento no gateway, se disponível

class ConnectionEvent(BaseModel):
    status: ConnectionStatus  # connected | disconnected | auth_expired | reconnecting | unknown
    detail: str = ""

class DeliveryAck(BaseModel):
    external_id: str
    status: DeliveryStatus  # sent | delivered | read | failed
```

Toda mensagem recebida vira um `InboundMessage`; toda mudança de sessão vira um
`ConnectionEvent`; toda confirmação de entrega vira um `DeliveryAck`. Um novo
Provider só precisa saber converter o formato do seu gateway para esses três
tipos — o resto (persistência, memória, resposta automática, métricas) já
existe e funciona automaticamente.

## Passo a passo

1. Crie `providers/whatsapp/<nome>/provider.py` com uma classe que estende
   `WhatsAppProvider` e implementa os 5 métodos de envio + `parse_webhook`.
2. Implemente `parse_connection_event`/`parse_delivery_ack` **apenas** se o
   gateway realmente reportar esses eventos no mesmo webhook (ver a
   implementação de referência em `openwa/provider.py`); caso contrário deixe
   o default (retorna `None`, ou seja "este provider não relata isso").
3. Use o helper `self._request(method, url, json_body=..., headers=...)`
   herdado da base para toda chamada HTTP ao gateway — ele já dá retry com
   backoff exponencial, métricas de disponibilidade
   (`darioos_whatsapp_provider_requests_total`) e tradução de erro uniforme
   de graça. Não use `httpx` diretamente no seu Provider.
4. Se o gateway expuser um endpoint de status de conexão, sobrescreva
   `health_check()` — mas passe `max_attempts=1` na chamada a `_request`
   (um readiness probe precisa responder rápido mesmo com o gateway fora do
   ar; retry pertence às operações de envio, não a uma sondagem de saúde).
5. Se o gateway assinar criptograficamente o webhook, sobrescreva
   `verify_signature` (ver `official/provider.py` para o HMAC-SHA256 da Meta).
   Sem isso, o webhook continua protegido pelo `WEBHOOK_SECRET` compartilhado
   verificado na rota.
6. Registre a classe em `providers/whatsapp/factory.py` (`_PROVIDERS`).
7. Selecione com `WHATSAPP_PROVIDER=<nome>` — pronto, nenhuma outra mudança.

## Exemplo mínimo

```python
# providers/whatsapp/meugateway/provider.py
from providers.whatsapp.base import InboundMessage, WhatsAppProvider, normalize_phone


class MeuGatewayProvider(WhatsAppProvider):
    name = "meugateway"

    def __init__(self) -> None:
        from utils.config import get_settings
        self._base_url = get_settings().meugateway_base_url.rstrip("/")

    async def send_text(self, to: str, content: str) -> dict:
        return await self._request(
            "POST", f"{self._base_url}/send",
            json_body={"to": normalize_phone(to), "text": content},
        )

    async def send_image(self, to, url, filename="image", caption="") -> dict:
        return await self._request("POST", f"{self._base_url}/send-media",
            json_body={"to": normalize_phone(to), "url": url, "caption": caption})

    async def send_file(self, to, url, filename="file", caption="") -> dict:
        return await self._request("POST", f"{self._base_url}/send-media",
            json_body={"to": normalize_phone(to), "url": url, "caption": caption})

    async def send_audio(self, to, url) -> dict:
        return await self._request("POST", f"{self._base_url}/send-media",
            json_body={"to": normalize_phone(to), "url": url})

    async def send_location(self, to, latitude, longitude, caption="") -> dict:
        return await self._request("POST", f"{self._base_url}/send-location",
            json_body={"to": normalize_phone(to), "lat": latitude, "lng": longitude})

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        if payload.get("type") != "message":
            return None
        return InboundMessage(
            phone=normalize_phone(str(payload["from"])),
            text=str(payload.get("text", "")),
            sender_name=str(payload.get("name", "")),
            external_id=str(payload.get("id", "")),
        )
```

```python
# providers/whatsapp/factory.py
from providers.whatsapp.meugateway.provider import MeuGatewayProvider

_PROVIDERS = {
    ...,
    MeuGatewayProvider.name: MeuGatewayProvider,
}
```

## Checklist de testes (o que a suíte de compatibilidade já garante de graça)

`tests/test_whatsapp_provider_compatibility.py` roda uma bateria de testes
parametrizada contra **todo** Provider registrado na factory — inclusive o
seu, assim que ele for adicionado a `ALL_PROVIDER_CLASSES` nesse arquivo:

- `parse_webhook`/`parse_connection_event`/`parse_delivery_ack` nunca lançam
  exceção com payload malformado (`{}`, chaves ausentes, `null` onde se
  esperava um dict) — sempre retornam `None` ou o modelo esperado.
- `verify_signature` sempre devolve um `bool`.
- `health_check()` sempre devolve um `bool`, mesmo apontando para um gateway
  inalcançável (nunca propaga uma exceção de conexão).
- Os 5 métodos de envio existem e são chamáveis.
- O provider está registrado na factory pelo seu próprio `name`.

Além disso, o arquivo prova a regra central (substituição de gateway é
configuração, não código) registrando um `_FakeProvider` minúsculo — nunca
visto antes pela aplicação — e mostrando que a rota de webhook e o envio
funcionam através dele sem alterar uma linha de `webhooks/router.py` ou
`api/whatsapp.py`.

Ao adicionar um Provider novo, o mínimo recomendado:

1. Adicione a classe a `ALL_PROVIDER_CLASSES` em
   `tests/test_whatsapp_provider_compatibility.py` — a bateria de contrato
   roda automaticamente para ela.
2. Adicione um teste de normalização de payload realista (não só de garbage
   input) em `tests/test_providers.py`, no estilo de
   `test_openwa_webhook_normalization`/`test_evolution_webhook_normalization`.
3. Rode `pytest -q` — a suíte inteira, incluindo os testes de segurança do
   webhook (`tests/test_webhook_security.py`) e do fluxo ponta a ponta
   (`tests/test_whatsapp_pipeline.py`), deve continuar passando sem
   modificação: essa é a prova de que o novo Provider não exigiu tocar em
   nenhuma outra camada.

## Reconexão, sessão e confiabilidade

- **Reconexão automática / perda de sessão**: gateways baseados em
  WhatsApp Web (OpenWA, Baileys, Evolution) não podem reconectar sozinhos uma
  sessão deslogada — isso exige re-parear o dispositivo (escanear o QR code
  novamente), uma ação humana por natureza. O Provider reporta o estado via
  `parse_connection_event` (`AUTH_EXPIRED`, `RECONNECTING`, ...); a aplicação
  registra o evento (log + métrica + Event Bus `whatsapp.session_changed`) e,
  para `AUTH_EXPIRED`, emite um log de erro claro pedindo intervenção humana.
  Não finja uma reconexão automática que a tecnologia subjacente não oferece.
- **Retry com backoff exponencial**: automático para toda chamada HTTP feita
  através de `self._request(...)` — configurável via
  `WHATSAPP_REQUEST_MAX_ATTEMPTS`/`WHATSAPP_REQUEST_BACKOFF_SECONDS`. Passe
  `max_attempts=1` para chamadas que precisam responder rápido (ex.: um
  readiness probe).
- **Mensagens duplicadas**: tratadas uma única vez, no webhook
  (`webhooks/router.py`), por `external_id` — não é responsabilidade do
  Provider.
- **Mensagens fora de ordem**: o Provider deve preencher `InboundMessage.timestamp`
  quando o gateway informar a hora do evento; `MessageRepository.recent_for_contact`
  ordena por esse timestamp (com fallback para a ordem de chegada quando
  ausente), então o histórico de conversa fica cronológico mesmo com
  redeliveries fora de ordem.
- **Confirmação de entrega**: implemente `parse_delivery_ack` se o gateway
  suportar; caso contrário deixe o default (`None`) — nem toda tecnologia de
  transporte tem esse recurso.
- **Logs estruturados e métricas de disponibilidade**: de graça via
  `self._request` (`darioos_whatsapp_provider_requests_total{provider,status}`)
  e via `health_check()` alimentando `darioos_whatsapp_session_status{provider}`
  (checado por `/health/ready`).
