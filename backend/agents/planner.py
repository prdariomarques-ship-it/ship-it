"""Planner: assembles the working context for an agent run.

Turns the agent's identity, permanent-memory hits and the user request into
the initial message list the executor iterates on.
"""
from providers.llm.base import ChatMessage


class Planner:
    def build_messages(
        self,
        system_prompt: str,
        message: str,
        memories: list[dict] | None = None,
        history: list[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        prompt = system_prompt
        if memories:
            lines = [f"- ({memory.get('source', '?')}) {memory.get('content', '')}" for memory in memories]
            prompt += "\n\nMemórias relevantes sobre o assunto:\n" + "\n".join(lines)
        prompt += (
            "\n\nQuando precisar consultar ou alterar dados, use as ferramentas disponíveis "
            "em vez de inventar informações. Após usar as ferramentas necessárias, "
            "responda ao usuário em português brasileiro."
        )

        messages: list[ChatMessage] = [ChatMessage(role="system", content=prompt)]
        messages.extend(history or [])
        messages.append(ChatMessage(role="user", content=message))
        return messages
