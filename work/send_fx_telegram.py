import json
import os
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


if os.name == "nt":
    PROJECT_ROOT = Path(os.getenv("MARKET_AGENT_PROJECT_ROOT", r"C:\Users\dario\OneDrive\Documents\New project"))
else:
    PROJECT_ROOT = Path(os.getenv("MARKET_AGENT_PROJECT_ROOT", Path.cwd()))
ENV_PATH = PROJECT_ROOT / ".env"
STATE_DIR = PROJECT_ROOT / ".state"
LOG_PATH = STATE_DIR / "scheduler.log"
TELEGRAM_API_BASE = "https://api.telegram.org"


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = dict(os.environ)
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'").strip()
    return values


def request_json(url: str, timeout: int = 8) -> dict:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fmt_brl(value: str | float | None) -> str:
    if value is None:
        return "n/d"
    number = float(value)
    text = f"{number:,.4f}"
    return "R$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value: str | float | None) -> str:
    if value is None:
        return "n/d"
    number = float(value)
    prefix = "+" if number > 0 else ""
    text = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefix}{text}%"


def load_fx_quotes() -> list[dict]:
    pairs = "USD-BRL,EUR-BRL,GBP-BRL,CHF-BRL,JPY-BRL,EUR-USD"
    url = f"https://economia.awesomeapi.com.br/last/{pairs}"
    payload = request_json(url)

    names = {
        "USDBRL": "Dolar comercial",
        "EURBRL": "Euro",
        "GBPBRL": "Libra",
        "CHFBRL": "Franco suico",
        "JPYBRL": "Iene",
        "EURUSD": "Euro/Dolar",
    }

    quotes = []
    for key, name in names.items():
        item = payload.get(key)
        if not item:
            continue
        quotes.append(
            {
                "name": name,
                "bid": item.get("bid"),
                "pct": item.get("pctChange"),
                "high": item.get("high"),
                "low": item.get("low"),
            }
        )
    return quotes


def send_telegram(token: str, chat_id: str, text: str) -> None:
    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(
        f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=10):
        return


def main() -> int:
    log("Iniciando bot de cambio.")
    env = load_env(ENV_PATH)
    token = env.get("TELEGRAM_FX_BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_FX_CHAT_ID") or env.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log("Telegram cambio: erro - token ou chat ausente.")
        return 1

    try:
        quotes = load_fx_quotes()
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        log(f"Telegram cambio: erro ao buscar cambio - {error}.")
        quotes = []

    lines = [
        f"Bot Cambio - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "",
        "Dolar, euro e moedas:",
    ]

    if quotes:
        for quote in quotes:
            lines.append(f"- {quote['name']}: {fmt_brl(quote['bid'])} ({fmt_pct(quote['pct'])})")
        lines.append("")
        lines.append("Faixa do dia em USD/BRL e EUR/BRL: conferir maximas/minimas se houver volatilidade forte.")
        lines.append("Fonte: AwesomeAPI Economia.")
    else:
        lines.extend(
            [
                "- Dolar comercial (USD/BRL)",
                "- Euro (EUR/BRL)",
                "- Libra, franco suico, iene e Euro/Dolar",
                "",
                "Fonte de cambio indisponivel neste ciclo; mantendo radar de moedas ativo.",
            ]
        )

    try:
        send_telegram(token, chat_id, "\n".join(lines))
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        log(f"Telegram cambio: erro no envio - {error}.")
        return 1

    log("Telegram cambio: 1 mensagem enviada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
