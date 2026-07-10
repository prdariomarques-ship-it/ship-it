# Visão — Dario OS

> Este é um documento vivo. Ele descreve o propósito e os princípios do projeto tal como estabelecidos até a v1.0 — deve ser revisado e ajustado pelo dono do produto conforme o projeto evolui, não tratado como definitivo.

## Missão

Dario OS é um sistema operacional pessoal baseado em IA: uma única plataforma onde WhatsApp, agenda, tarefas, loja, igreja e memória permanente convergem, com agentes de IA que pensam antes de agir em vez de executar regras fixas.

O problema que resolve: hoje, atender clientes/contatos pelo WhatsApp, gerenciar agenda e tarefas, tocar uma loja ou uma igreja e manter memória de tudo isso normalmente significa várias ferramentas desconectadas, nenhuma delas com contexto das outras. Dario OS centraliza isso em um único sistema que lembra, entende intenção e prioridade, e age através dos domínios certos — sem exigir que o dono opere cada canal manualmente.

## Para quem é

Um sistema de **dono único**. Não é uma plataforma multi-tenant, não é um SaaS para múltiplas empresas — é o assistente pessoal/de negócio de uma pessoa (ou de uma operação pequena, como uma loja ou uma igreja administrada por um dono), que se conecta ao WhatsApp desse dono e age em nome dele. Contatos que escrevem para esse número não são "usuários do sistema" — são pessoas que o assistente atende em nome do dono.

## Princípios (não negociáveis, guiaram cada fase deste projeto)

1. **Simplicidade antes de sofisticação.** Uma solução simples e robusta vence uma elegante e frágil. Complexidade só é adicionada quando resolve um problema real e comprovado, nunca por antecipação.
2. **Robustez comprovada por teste, não por alegação.** Nenhuma capacidade é considerada pronta sem um teste automatizado provando o comportamento — inclusive os caminhos de falha (provider fora do ar, banco indisponível, mensagem duplicada, fora de ordem).
3. **Desacoplamento onde importa.** Trocar de provider de WhatsApp, de modelo de LLM, ou adicionar um agente novo deve ser configuração, não uma reescrita. A plataforma existe para que essas peças sejam substituíveis sem tocar no núcleo.
4. **Compatibilidade total entre evoluções.** Cada fase deste projeto foi construída sem quebrar o que a fase anterior já entregava. Migração de arquitetura é aditiva, não destrutiva.
5. **Pensar antes de agir.** A partir do Cognitive Pipeline (Fase 4.2), o sistema classifica intenção e prioridade, planeja, valida sua própria resposta e aprende com a conversa — em vez de mapear cada mensagem a uma regra fixa de `if/else`.
6. **Segurança é parte do produto, não um anexo.** Decisões de autorização (quem um agente pode contatar, o que pode fazer) vivem no código, nunca dependem só de uma instrução de prompt ao modelo — estabelecido explicitamente na correção de PROD-004/PROD-005 antes da aprovação da v1.0.
7. **Nada é lançado sem ser auditado com rigor.** A v1.0 só foi aprovada para produção depois de uma auditoria adversarial formal (`PRODUCTION_APPROVAL.md`) que encontrou e exigiu a correção de bloqueadores reais antes do sinal verde.

## O que o Dario OS é

- Um orquestrador cognitivo de agentes especializados (pessoal, loja, igreja, conteúdo, um assistente geral) que compartilham memória, ferramentas e infraestrutura comuns.
- Um sistema operacional no sentido literal: a camada que decide qual agente, qual ferramenta, qual memória e qual prioridade cada mensagem recebe — não um chatbot de domínio único.
- Uma plataforma auto-hospedada (Docker Compose), sob controle total do dono, sem dependência de um provedor externo para funcionar.
- Extensível por convenção: um agente ou ferramenta novos entram adicionando um arquivo, sem editar um registro central.

## O que o Dario OS não é (por decisão, não por limitação técnica)

- Não é uma plataforma multi-tenant ou um produto SaaS para terceiros administrarem seus próprios clientes dentro da mesma instância.
- Não é um construtor de chatbots genérico — os agentes e ferramentas existentes refletem os domínios reais do dono (agenda, loja, igreja, conteúdo), não um framework para qualquer caso de uso.
- Não persegue "inteligência" como métrica em si — cada capacidade cognitiva adicionada (classificação de intenção, planejamento, validação, aprendizado) existe para resolver um problema concreto do fluxo de atendimento, comprovado por teste, não para parecer mais avançado.

## Onde está hoje (v1.0)

Plataforma completa, aprovada para produção: Agent Registry, Tool Registry, Event Bus, AI Orchestrator, Memory Manager, Providers plugáveis de LLM (5) e WhatsApp (4), fila de jobs durável, e o Cognitive Pipeline (intenção, prioridade, planejamento, validação, aprendizado) processando o fluxo de WhatsApp ponta a ponta. 246 testes automatizados, documentação operacional completa (`OPERATIONS.md` e relacionados). Ver `RELEASE_NOTES_v1.0.md` para o detalhe técnico completo.

## Para onde vai

O backlog priorizado da v1.1 (`ROADMAP_v1.1.md`) reflete a mesma lógica de sempre: primeiro fechar lacunas operacionais reais (backup completo, monitoramento, rotação de log — P0/P1), depois evoluir a capacidade cognitiva onde há valor comprovado (retomada de plano pendente, ingestão de conhecimento real — P2), nunca adicionar capacidade por completude. Este documento deve ser revisitado a cada versão maior para confirmar que a direção ainda reflete a intenção do dono do produto.
