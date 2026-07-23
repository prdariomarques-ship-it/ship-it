# Security Review — Contact Priority Panel / P0-4 Recommendations

## Resultado direto

**Esta feature introduz alguma superfície de ataque nova? NÃO.**

Toda linha nova de código ou (a) lê dado já autorizado e já carregado, ou
(b) renderiza texto React já escapado por padrão. O único gap real
encontrado (rate limiting ausente no endpoint de execução) é pré-existente
a esta feature, não introduzido por ela — já sinalizado no P0-2/P0-3/P0-4
original, repetido aqui por completude, não como novidade.

## Checklist

| Item | Resultado |
|---|---|
| Authentication | Inalterado, continua exigido |
| Authorization | Inalterado, continua exigido |
| RBAC | Inalterado — modelo de role única (`ADMIN`), não tocado |
| Horizontal privilege escalation | Não aplicável — Contacts é recurso compartilhado, não pertence a um usuário específico, por design já existente (`models/contact.py`) |
| Vertical privilege escalation | Impossível — nenhuma lógica de role/permissão tocada |
| Input validation | Nenhum input novo introduzido |
| Output encoding | Escapamento padrão do JSX cobre todo texto novo renderizado |
| XSS | Nenhum `dangerouslySetInnerHTML` em qualquer arquivo tocado |
| CSRF | Não aplicável — modelo de autenticação via Bearer token em header, nunca cookie ambiente |
| SSRF | Não aplicável — nenhuma chamada HTTP de saída nova introduzida |
| SQL Injection | Não aplicável — a única linha nova (`contact.last_interaction_at`) lê um atributo ORM já carregado, zero construção de query nova |
| Command Injection | Não aplicável — nenhuma chamada de shell/subprocess em qualquer arquivo tocado |
| Mass Assignment | Não aplicável — nenhum endpoint de escrita novo, nenhum schema de request body novo |
| Sensitive logging | Inalterado — execução de recomendação já é auditada via `record_log` (pré-existente), loga a explicação e o resultado, nenhum PII novo logado |
| PII exposure | O único campo novo (`last_interaction_at`) é um timestamp, já implicitamente acessível via `/contacts/{id}/workspace` |
| Secrets | Nenhum em qualquer arquivo tocado |
| Cookies | Não usados por este modelo de autenticação |
| Headers | Nenhum header novo introduzido |
| CORS | Inalterado |
| Rate limiting | **Gap confirmado** — nem `/contacts/priority` nem o endpoint de execução têm rate limiting dedicado; pré-existente, não introduzido aqui |
| Replay attacks | O endpoint de execução já re-deriva a recomendação a partir de dados vivos antes de despachar (guarda de staleness, pré-existente) — uma requisição repetida ou faz nada (recomendação não se aplica mais) ou reexecuta uma ação ainda válida; trade-off aceito antes desta feature, não um risco novo |
| Denial of service | O único vetor relevante é a ausência de rate limiting no endpoint de execução, já coberto acima |
| Dependency risks | Nenhuma dependência nova adicionada neste diff |

## Recomendação

Fechar o gap de rate limiting no endpoint de execução (`POST
/contacts/{id}/recommendations/{id}/execute`) antes de qualquer exposição
multi-usuário do sistema — reaproveitando `services/rate_limit.py`, já
usado em `auth/router.py`. Esforço baixo, não bloqueante para o uso atual
de usuário único.
