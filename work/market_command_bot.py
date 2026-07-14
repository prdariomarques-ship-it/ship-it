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
OFFSET_PATH = STATE_DIR / "telegram_command_offset.json"
TELEGRAM_API_BASE = "https://api.telegram.org"


ASSETS = {
    "indices": [
        ("IBOV", "Ibovespa"),
        ("IBRX100", "IBrX-100"),
        ("SMLL", "Small Caps"),
        ("IDIV", "Dividendos"),
        ("IFIX", "Fundos Imobiliarios"),
        ("IEE", "Energia Eletrica"),
    ],
    "acoes": [
        ("PETR4", "Petrobras PN"), ("VALE3", "Vale ON"), ("ITUB4", "Itau Unibanco PN"),
        ("BBDC4", "Bradesco PN"), ("ABEV3", "Ambev ON"), ("WEGE3", "WEG ON"),
        ("BBAS3", "Banco do Brasil ON"), ("B3SA3", "B3 ON"), ("RENT3", "Localiza ON"),
        ("MGLU3", "Magazine Luiza ON"), ("ELET3", "Eletrobras ON"), ("SUZB3", "Suzano ON"),
        ("EQTL3", "Equatorial ON"), ("LREN3", "Lojas Renner ON"), ("HAPV3", "Hapvida ON"),
    ],
    "etfs": [
        ("BOVA11", "Ibovespa"), ("SMAL11", "Small Caps"), ("IVVB11", "S&P 500"),
        ("DIVO11", "Dividendos"), ("FIXA11", "Renda Fixa"), ("GOLD11", "Ouro"),
        ("NASD11", "Nasdaq 100"),
    ],
    "fiis": [
        ("HGLG11", "Logistica"), ("KNRI11", "Hibrido"), ("XPLG11", "Logistica"),
        ("VISC11", "Shoppings"), ("MXRF11", "Papel"),
    ],
    "bdrs": [
        ("AAPL34", "Apple"), ("MSFT34", "Microsoft"), ("AMZO34", "Amazon"),
        ("GOOG34", "Alphabet"), ("TSLA34", "Tesla"), ("NVDC34", "Nvidia"),
    ],
    "derivativos": [
        ("IND", "Futuro de Ibovespa"), ("DOL", "Futuro de dolar"), ("DI", "DI futuro"),
        ("PETR4 Opcoes", "Calls/puts mais negociadas"), ("VALE3 Opcoes", "Calls/puts mais negociadas"),
    ],
}

FIXED_INCOME = [
    "Selic meta e efetiva",
    "CDI diario e acumulado",
    "IPCA mensal e acumulado em 12 meses",
    "IGP-M",
    "Tesouro Direto: Prefixado, Selic e IPCA+",
    "DI futuro: principais vertices",
]

FX_PAIRS = {
    "USDBRL": "Dolar comercial",
    "EURBRL": "Euro",
    "GBPBRL": "Libra",
    "ARSBRL": "Peso argentino",
    "JPYBRL": "Iene",
}


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


def request_json(url: str, timeout: int = 10) -> dict:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def telegram_request(token: str, method: str, data: dict | None = None) -> dict:
    url = f"{TELEGRAM_API_BASE}/bot{token}/{method}"
    if data is None:
        return request_json(url)
    payload = urlencode(data).encode("utf-8")
    request = Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(token: str, chat_id: str | int, text: str) -> None:
    telegram_request(token, "sendMessage", {"chat_id": str(chat_id), "text": text[:3900], "disable_web_page_preview": "true"})


def read_offset() -> int:
    if not OFFSET_PATH.exists():
        return 0
    try:
        return int(json.loads(OFFSET_PATH.read_text(encoding="utf-8")).get("offset", 0))
    except (ValueError, json.JSONDecodeError):
        return 0


def write_offset(offset: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def fmt_number(value: str | float | None, decimals: int = 4) -> str:
    if value is None:
        return "n/d"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value: str | float | None) -> str:
    if value is None:
        return "n/d"
    number = float(value)
    prefix = "+" if number > 0 else ""
    return f"{prefix}{fmt_number(number, 2)}%"


def asset_lines(group: str) -> list[str]:
    return [f"- {symbol}: {name}" for symbol, name in ASSETS[group]]


def response_help() -> str:
    return "\n".join([
        "Comandos do bot de mercado:", "",
        "/mercado - visao geral dos grupos monitorados",
        "/indices - IBOV, IBrX-100, SMLL, IDIV, IFIX, IEE",
        "/acoes - acoes brasileiras monitoradas",
        "/etfs - ETFs monitorados",
        "/fiis - FIIs monitorados",
        "/bdrs - BDRs monitorados",
        "/rendafixa - Selic, CDI, IPCA, IGP-M, Tesouro e DI",
        "/cambio - dolar, euro, libra, peso argentino e iene",
        "/derivativos - IND, DOL, DI e opcoes PETR4/VALE3",
        "/spcx - SPCX sem misturar com o radar brasileiro",
    ])


def response_market() -> str:
    return "\n".join([
        f"Mercado Brasil - {datetime.now().strftime('%d/%m/%Y %H:%M')}", "",
        "Monitoramento ampliado:",
        f"- Indices: {len(ASSETS['indices'])}",
        f"- Acoes: {len(ASSETS['acoes'])}",
        f"- ETFs: {len(ASSETS['etfs'])}",
        f"- FIIs: {len(ASSETS['fiis'])}",
        f"- BDRs: {len(ASSETS['bdrs'])}",
        f"- Derivativos: {len(ASSETS['derivativos'])}",
        "- Renda fixa: Selic, CDI, IPCA, IGP-M, Tesouro Direto e DI",
        "- Cambio: USD, EUR, GBP, ARS e JPY contra BRL", "",
        "Use /help para ver os comandos.",
    ])


def response_group(title: str, group: str) -> str:
    return "\n".join([title, ""] + asset_lines(group))


def response_fixed_income() -> str:
    return "\n".join(["Renda fixa no radar:", ""] + [f"- {item}" for item in FIXED_INCOME])


def response_spcx() -> str:
    return "\n".join([
        "SPCX no radar separado:", "",
        "- Mantido fora do bloco principal brasileiro para evitar duplicacao.",
        "- Usar para noticias/eventos relevantes ligados a SPCX, SpaceX, Starlink e Tesla.",
        "- O outro bot continua cobrindo mercado brasileiro, cambio e renda fixa.",
    ])


def response_fx() -> str:
    pairs = "USD-BRL,EUR-BRL,GBP-BRL,ARS-BRL,JPY-BRL"
    url = f"https://economia.awesomeapi.com.br/last/{pairs}"
    try:
        payload = request_json(url)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return "\n".join(["Cambio no radar:", "", "- USD/BRL comercial e turismo", "- EUR/BRL", "- GBP/BRL", "- ARS/BRL", "- JPY/BRL", "", "Fonte de cotacao indisponivel neste momento."])

    lines = [f"Cambio - {datetime.now().strftime('%d/%m/%Y %H:%M')}", ""]
    for key, label in FX_PAIRS.items():
        quote = payload.get(key)
        if quote:
            lines.append(f"- {label}: R$ {fmt_number(quote.get('bid'))} ({fmt_pct(quote.get('pctChange'))})")
    lines.append("")
    lines.append("Fonte: AwesomeAPI Economia.")
    return "\n".join(lines)


def route_command(text: str) -> str | None:
    command = text.strip().split()[0].split("@")[0].lower()
    routes = {
        "/start": response_help,
        "/help": response_help,
        "/mercado": response_market,
        "/indices": lambda: response_group("Indices monitorados:", "indices"),
        "/acoes": lambda: response_group("Acoes monitoradas:", "acoes"),
        "/etfs": lambda: response_group("ETFs monitorados:", "etfs"),
        "/fiis": lambda: response_group("FIIs monitorados:", "fiis"),
        "/bdrs": lambda: response_group("BDRs monitorados:", "bdrs"),
        "/rendafixa": response_fixed_income,
        "/cambio": response_fx,
        "/derivativos": lambda: response_group("Derivativos no radar:", "derivativos"),
        "/spcx": response_spcx,
    }
    handler = routes.get(command)
    if not handler:
        return None
    return handler()


def main() -> int:
    env = load_env(ENV_PATH)
    token = env.get("TELEGRAM_BOT_TOKEN")
    allowed_chat = env.get("TELEGRAM_CHAT_ID")
    if not token:
        log("Telegram comandos: erro - token ausente.")
        return 1

    offset = read_offset()
    params = {"timeout": "0"}
    if offset:
        params["offset"] = str(offset)

    try:
        updates = telegram_request(token, "getUpdates", params).get("result", [])
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        log(f"Telegram comandos: erro getUpdates - {error}.")
        return 1

    handled = 0
    max_update_id = offset - 1 if offset else 0
    for update in updates:
        update_id = int(update.get("update_id", 0))
        max_update_id = max(max_update_id, update_id)
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = message.get("text") or ""
        if not chat_id or not text.startswith("/"):
            continue
        if allowed_chat and str(chat_id) != str(allowed_chat):
            continue
        response = route_command(text)
        if response:
            send_message(token, chat_id, response)
            handled += 1

    if max_update_id:
        write_offset(max_update_id + 1)
        telegram_request(token, "getUpdates", {"offset": str(max_update_id + 1), "timeout": "0"})
    log(f"Telegram comandos: {handled} comando(s) respondido(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
