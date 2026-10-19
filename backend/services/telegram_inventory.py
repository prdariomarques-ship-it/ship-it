"""Audited inventory of the Telegram bots around Dario OS (read-only, static).

This is NOT live state. It is what was proven from source code and public repository pages on
`INVENTORY_AS_OF`, with the evidence recorded next to each claim. Nothing here starts, stops, or
talks to a bot; Dario OS holds no Telegram credential. `tests/test_telegram_inventory.py` keeps the
ship-it entries honest by checking them against the real scripts and workflow files, so a script or
workflow change that is not reflected here fails CI instead of silently drifting.

Runtime status vocabulary (never "unknown rendered as ok"):
  ativo_evidenciado -- a dated, linkable observation shows scheduled runs succeeding
  sem_agendamento   -- code exists but nothing schedules it (manual dispatch only)
  nao_verificado    -- code exists; whether anything runs it was not observed
  inconclusivo      -- no code, service or specification was found
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

INVENTORY_AS_OF = "2026-10-19"
SHIP_IT_REPO = "https://github.com/prdariomarques-ship-it/ship-it"

RuntimeStatus = Literal["ativo_evidenciado", "sem_agendamento", "nao_verificado", "inconclusivo"]


class Trigger(BaseModel):
    kind: Literal["schedule", "manual", "continuous"]
    expression: str | None = None
    host: str


class Runtime(BaseModel):
    status: RuntimeStatus
    detail: str
    evidence: str | None = None
    as_of: str | None = None


class TelegramBot(BaseModel):
    id: str
    name: str
    scope: Literal["ship-it", "externo"]
    repository: str | None = None
    source_files: list[str] = Field(default_factory=list)
    kind: Literal["command_poller", "push_report", "gateway", "unknown"]
    purpose: str
    commands: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    credentials: list[str] = Field(default_factory=list, description="Environment variable NAMES only; never values.")
    triggers: list[Trigger] = Field(default_factory=list)
    runtime: Runtime
    risks: list[str] = Field(default_factory=list)


class TelegramInventory(BaseModel):
    as_of: str
    live_state_available: bool
    live_state_note: str
    bots: list[TelegramBot]
    counts_by_runtime_status: dict[str, int]


POLLER_COMMANDS = [
    "/start", "/help", "/mercado", "/indices", "/acoes", "/etfs", "/fiis", "/bdrs",
    "/rendafixa", "/cambio", "/derivativos", "/spcx",
]

_BOTS: tuple[TelegramBot, ...] = (
    TelegramBot(
        id="market-command-poller",
        name="Bot de comandos de mercado",
        scope="ship-it",
        repository=SHIP_IT_REPO,
        source_files=["work/market_command_bot.py", ".github/workflows/telegram-commands.yml"],
        kind="command_poller",
        purpose=(
            "Responde comandos no chat autorizado. Só /cambio consulta cotações; os demais comandos devolvem "
            "listas estáticas de ativos monitorados (sem preços) e /spcx devolve um texto fixo."
        ),
        commands=POLLER_COMMANDS,
        data_sources=["AwesomeAPI Economia (somente /cambio)"],
        credentials=["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
        triggers=[
            Trigger(kind="schedule", expression="3/5 * * * *", host="GitHub Actions (workflow telegram-commands)"),
            Trigger(kind="manual", host="GitHub Actions (workflow_dispatch)"),
        ],
        runtime=Runtime(
            status="ativo_evidenciado",
            detail=(
                "Execuções agendadas na branch master concluídas com sucesso, as mais recentes no dia da auditoria. "
                "Sucesso do workflow não prova que cada resposta chegou ao Telegram."
            ),
            evidence=(
                f"{SHIP_IT_REPO}/actions/workflows/telegram-commands.yml "
                "(página pública; 1.411 execuções, última #1411)"
            ),
            as_of=INVENTORY_AS_OF,
        ),
        risks=[
            "Um único consumidor de getUpdates por token: outro processo com o mesmo token causa 409 "
            "e respostas perdidas ou duplicadas.",
            "A confirmação do offset ocorre depois das respostas: uma queda no meio pode repetir um comando "
            "(pelo menos uma vez).",
            "Sem TELEGRAM_CHAT_ID o poller agora não responde a ninguém (fail-closed).",
        ],
    ),
    TelegramBot(
        id="fx-radar",
        name="Radar de câmbio",
        scope="ship-it",
        repository=SHIP_IT_REPO,
        source_files=["work/send_fx_telegram.py", ".github/workflows/telegram-fx.yml"],
        kind="push_report",
        purpose=(
            "Envia uma mensagem com USD, EUR, GBP, CHF, JPY e EUR/USD; "
            "sem cotação disponível envia só a lista de moedas."
        ),
        data_sources=["AwesomeAPI Economia"],
        credentials=["TELEGRAM_FX_BOT_TOKEN (ou TELEGRAM_BOT_TOKEN)", "TELEGRAM_FX_CHAT_ID (ou TELEGRAM_CHAT_ID)"],
        triggers=[Trigger(kind="manual", host="GitHub Actions (workflow_dispatch)")],
        runtime=Runtime(
            status="sem_agendamento",
            detail=(
                "O workflow atual só roda por disparo manual. As execuções agendadas anteriores (38 no total) falharam "
                "todas as visíveis, a última em 2026-07-17; a causa não foi investigada."
            ),
            evidence=f"{SHIP_IT_REPO}/actions/workflows/telegram-fx.yml (página pública)",
            as_of=INVENTORY_AS_OF,
        ),
        risks=[
            "Pode haver agendamento fora do repositório (o script tem caminho de Windows); não foi verificado.",
        ],
    ),
    TelegramBot(
        id="market-radar",
        name="Radar de mercado diversificado",
        scope="ship-it",
        repository=SHIP_IT_REPO,
        source_files=["work/send_market_telegram.py", ".github/workflows/telegram-market.yml"],
        kind="push_report",
        purpose=(
            "Envia a lista de símbolos de um bloco rotativo (SPCX, NVDA, TSLA, índices). Não busca nem envia "
            "preços: a mensagem contém apenas nomes e símbolos."
        ),
        data_sources=[],
        credentials=["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
        triggers=[Trigger(kind="manual", host="GitHub Actions (workflow_dispatch)")],
        runtime=Runtime(
            status="sem_agendamento",
            detail=(
                "O workflow atual só roda por disparo manual. As execuções agendadas anteriores (42 no total) falharam "
                "todas as visíveis, a última em 2026-07-17; a causa não foi investigada."
            ),
            evidence=f"{SHIP_IT_REPO}/actions/workflows/telegram-market.yml (página pública)",
            as_of=INVENTORY_AS_OF,
        ),
        risks=["Não fornece dado de mercado; não deve ser apresentado como monitoramento de preços."],
    ),
    TelegramBot(
        id="dmarques-gateway",
        name="@Dmarques_bot (gateway para o Hermes)",
        scope="externo",
        repository="https://github.com/prdariomarques-ship-it/agente-dmn",
        source_files=["README.md (repositório externo)"],
        kind="gateway",
        purpose=(
            "Segundo o README: bot por long polling, responde só ao chat configurado; comandos /start e /help; "
            "o encaminhamento ao Hermes é um passo futuro."
        ),
        commands=["/start", "/help"],
        credentials=["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"],
        triggers=[Trigger(kind="continuous", host="processo Node.js 20+ (hospedagem não identificada)")],
        runtime=Runtime(
            status="nao_verificado",
            detail="Só o README foi lido; não há evidência de onde ou se o processo está rodando.",
            evidence="https://github.com/prdariomarques-ship-it/agente-dmn (repositório público)",
            as_of=INVENTORY_AS_OF,
        ),
        risks=["Se usar o mesmo token de outro bot, os dois consumidores de getUpdates se anulam (409)."],
    ),
    TelegramBot(
        id="renda-fixa-monitor",
        name="Monitor de renda fixa (IMA-B, IRF-M, IMA-B 5+)",
        scope="externo",
        repository="https://github.com/prdariomarques-ship-it/renda-fixa-monitor",
        source_files=["monitor_rf.py (repositório externo)"],
        kind="push_report",
        purpose=(
            "Resumo diário (variação no dia e em 12 meses) de três ETFs usados como proxy de índices de renda fixa, "
            "publicado no Telegram; sem dados, não envia."
        ),
        data_sources=["Yahoo Finance (yfinance): IMAB11.SA, IRFM11.SA, B5P211.SA"],
        credentials=["token e chat do Telegram (nomes não conferidos)"],
        triggers=[
            Trigger(
                kind="schedule",
                expression="seg-sex 20:30 America/Sao_Paulo",
                host="APScheduler no próprio processo (precisa ficar rodando)",
            )
        ],
        runtime=Runtime(
            status="nao_verificado",
            detail="Código lido; não há evidência de um processo hospedando o agendador.",
            evidence="https://github.com/prdariomarques-ship-it/renda-fixa-monitor (repositório público)",
            as_of=INVENTORY_AS_OF,
        ),
        risks=["Feriados brasileiros não são tratados; os ETFs são proxy e não reproduzem os índices ANBIMA."],
    ),
    TelegramBot(
        id="monitor-spcx",
        name="Monitor SCPX",
        scope="externo",
        kind="unknown",
        purpose="Citado como serviço de monitoramento, mas nenhum código, serviço ou especificação foi localizado.",
        runtime=Runtime(
            status="inconclusivo",
            detail=(
                "Sem código nos repositórios inspecionados (ship-it, agente-dmn, renda-fixa-monitor) "
                "nem no disco local. "
                "O comando /spcx do poller devolve apenas texto fixo e NÃO é esse monitor."
            ),
            as_of=INVENTORY_AS_OF,
        ),
        risks=["Não tratar como existente até que código ou serviço seja identificado."],
    ),
)


def build_inventory() -> TelegramInventory:
    bots = [bot.model_copy(deep=True) for bot in _BOTS]
    counts = Counter(bot.runtime.status for bot in bots)
    return TelegramInventory(
        as_of=INVENTORY_AS_OF,
        live_state_available=False,
        live_state_note=(
            "Inventário auditado e estático. O Dario OS não guarda credenciais do Telegram nem lê o estado do GitHub "
            "Actions, então o estado em tempo real não está disponível neste painel."
        ),
        bots=bots,
        counts_by_runtime_status=dict(counts),
    )
