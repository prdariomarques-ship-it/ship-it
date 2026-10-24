"""Quando o Gêmeo deve CALAR (sem resposta e sem mensagem de retenção).

Casos reais (16 a 23/10/2026, 223 respostas lidas): 79 respostas (35%) foram para outros robôs -- o assistente da igreja (54 trocas de
"👋"/"Até" minuto a minuto), o alerta do vigia de linhas (10 min de "Até.") e menus de cobrança/banco. Aqui só há regras puras, sem I/O:
quem decide agir (não enfileirar nada) é `jobs/handlers.twin_autopilot_check`.

Regras (todas conservadoras; errar para o lado de calar custa uma resposta que o dono dá em segundos):
  1. despedida/agradecimento puro, quando já existe uma fala anterior nossa na conversa ("🙏", "Até!", "Valeu!", "Amém!");
  2. texto típico de robô/menu/fila ("assistente virtual", "só um instante", "responderemos durante nosso horário", ...);
  3. alerta do próprio sistema ("[Gêmeo Darius]", "A linha X está FORA DO AR", "Teste do vigia", "não responda").
"""

import re

from orchestrator.twin_risk_gate import normalize_text

_CLOSING_WORDS = frozenset(
    "ate mais logo proxima valeu obrigado obrigada brigado tmj abraco abracos amem tchau blz ok certo show combinado fechado "
    "deus abencoe fica com voce vc tambem de nada imagina disponha disposicao tudo bom ta pra para".split()
)
_LAUGH = re.compile(r"^(?:k{2,}|(?:ha|he|rs){2,})$")
_BOT_PHRASES = tuple(
    normalize_text(p)
    for p in (
        "assistente virtual", "responderemos durante nosso horario", "so um instante", "so um minutinho", "so um segundinho",
        "aguarde um momento", "aguarde um pouquinho", "um momento, por favor", "vou encerrar nossa conversa",
        "como posso ajudar voce hoje", "atendimento automatico", "mensagem automatica", "quer continuar nossa negociacao",
        "voce foi transferido", "toque no botao", "digite o numero", "digite a opcao",
    )
)
_OWN_ALERT_PREFIXES = tuple(normalize_text(p) for p in ("[gemeo darius]", "teste do vigia", "alerta automatico"))
_LINE_ALERT_MARKERS = tuple(normalize_text(p) for p in ("fora do ar", "voltou (open)", "nao responda"))


def is_closing_only(text: str) -> bool:
    """Só emoji/pontuação, ou poucas palavras de despedida/agradecimento, sem pergunta e sem número."""
    raw = (text or "").strip()
    if not raw or "?" in raw or re.search(r"\d", raw):
        return False
    words = re.findall(r"[^\W\d_]+", normalize_text(raw))
    if not words:
        return True                                   # só emoji ou pontuação
    if len(words) > 8:
        return False
    return all(w in _CLOSING_WORDS or _LAUGH.match(w) for w in words)


def automated_text(text: str) -> bool:
    normalized = normalize_text(text or "")
    return any(p in normalized for p in _BOT_PHRASES)


def own_system_alert(text: str) -> bool:
    normalized = normalize_text(text or "").lstrip(" ✅⚠️")
    if normalized.startswith(_OWN_ALERT_PREFIXES):
        return True
    return "alerta automatico" in normalized or ("a linha " in normalized and any(m in normalized for m in _LINE_ALERT_MARKERS))


def silence_reason(text: str, *, has_prior_outbound: bool) -> str | None:
    """Motivo para NÃO responder, ou None. `has_prior_outbound`: já existe fala nossa (dono, Gêmeo ou outra) antes desta mensagem."""
    if own_system_alert(text):
        return "alerta_do_proprio_sistema"
    if automated_text(text):
        return "remetente_automatizado"
    if has_prior_outbound and is_closing_only(text):
        return "despedida_ou_agradecimento"
    return None
