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
    log("Iniciando panorama diversificado de mercado.")
    env = load_env(ENV_PATH)
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log("Telegram mercado diversificado: erro - token ou chat ausente.")
        return 1

    baskets = [
        [
            {"group": "eua", "name": "SPCX", "symbol": "SPCX"},
            {"group": "eua", "name": "Nvidia", "symbol": "NVDA"},
            {"group": "eua", "name": "Tesla", "symbol": "TSLA"},
        ],
        [
            {"group": "indices", "name": "Ibovespa", "symbol": "^BVSP"},
            {"group": "brasil", "name": "PETR4", "symbol": "PETR4.SA"},
            {"group": "brasil", "name": "VALE3", "symbol": "VALE3.SA"},
        ],
        [
            {"group": "indices", "name": "S&P 500", "symbol": "^GSPC"},
            {"group": "indices", "name": "Nasdaq", "symbol": "^IXIC"},
            {"group": "indices", "name": "Dow Jones", "symbol": "^DJI"},
        ],
        [
            {"group": "indices", "name": "FTSE 100", "symbol": "^FTSE"},
            {"group": "indices", "name": "KOSPI", "symbol": "^KS11"},
            {"group": "indices", "name": "Nikkei 225", "symbol": "^N225"},
        ],
    ]
    slot = (datetime.now().hour * 4 + datetime.now().minute // 15) % len(baskets)
    universe = baskets[slot]

    lines = [
        f"Radar diversificado - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "",
        "Bloco desta rodada:",
    ]
    lines.extend(f"- {item['name']} ({item['symbol']})" for item in universe)
    lines.append("")
    lines.append("Radar rotativo: SPCX, Nvidia, Tesla, Ibovespa, PETR4, VALE3, S&P 500, Nasdaq, Dow Jones, FTSE, KOSPI e Nikkei.")
    lines.append("Objetivo: evitar repeticao de SPCX e ampliar a cobertura entre indices globais e papeis relevantes.")

    try:
        send_telegram(token, chat_id, "\n".join(lines))
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        log(f"Telegram mercado diversificado: erro - {error}.")
        return 1

    log("Telegram mercado diversificado: 1 mensagem enviada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
