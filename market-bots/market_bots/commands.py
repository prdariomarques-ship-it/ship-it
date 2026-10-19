"""Maps a chat command to the messages to reply with. Authorization is NOT decided here (see runner)."""
from __future__ import annotations

from . import formatting as fmt
from .domain import Profile
from .service import MarketService


class CommandRouter:
    def __init__(self, profile: Profile, service: MarketService) -> None:
        self._p = profile
        self._svc = service
        self._sections = {s.id: s for s in profile.sections}

    def help_text(self) -> str:
        p = self._p
        lines = [f"{p.title}", "", "/mercado - boletim completo"]
        lines.extend(f"/{s.id} - {s.title}" for s in p.sections)
        if p.movers:
            lines.append("/altas - maiores altas e quedas")
        if p.filings:
            lines.append("/fatos - fatos relevantes (CVM)")
        if p.alerts:
            lines.append("/alertas - regras de alerta ativas")
        lines.append("/cotacao SIMBOLO - cotação avulsa (ex.: /cotacao PETR4.SA)")
        return "\n".join(lines)

    def alerts_text(self) -> str:
        if not self._p.alerts:
            return "Nenhuma regra de alerta configurada."
        lines = ["REGRAS DE ALERTA"]
        lines.extend(f"• {r.label or r.symbol}: variação diária ≥ ±{fmt.num(r.min_abs_change_pct, 1)}%" for r in self._p.alerts)
        if self._p.filings:
            lines.append("• Novo fato relevante na CVM")
        lines.append(f"Verificação a cada {self._p.alert_interval_minutes} min, "
                     f"{self._p.alert_window[0]}-{self._p.alert_window[1]} (dias úteis).")
        return "\n".join(lines)

    def handle(self, text: str) -> list[str]:
        parts = text.strip().split(maxsplit=1)
        if not parts or not parts[0].startswith("/"):
            return []
        cmd = parts[0][1:].split("@", 1)[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        if cmd in ("start", "ajuda", "help"):
            return [self.help_text()]
        if cmd == "mercado":
            return self._svc.bulletin(self._p)
        if cmd in self._sections:
            return [self._svc.section_message(self._sections[cmd])]
        if cmd == "altas" and self._p.movers:
            return [m for m in [self._svc.movers_message(self._p)] if m]
        if cmd == "fatos" and self._p.filings:
            return [m for m in [self._svc.filings_message(self._p)] if m]
        if cmd == "alertas":
            return [self.alerts_text()]
        if cmd == "cotacao":
            return [self._svc.quote_message(arg)] if arg else ["Use: /cotacao SIMBOLO (ex.: /cotacao PETR4.SA)"]
        return ["Comando desconhecido. Envie /ajuda."]
