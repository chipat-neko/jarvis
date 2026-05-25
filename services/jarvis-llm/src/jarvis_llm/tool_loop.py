"""Boucle de tool calling LLM ↔ executor.

Le LLM (via OllamaClient avec `tools=[...]`) peut demander d'appeler un outil.
On exécute l'outil (via un callable injecté), on ajoute le résultat à
l'historique, et on relance le LLM jusqu'à obtenir une réponse texte finale
(ou jusqu'à atteindre `max_iterations` pour éviter une boucle infinie).

Cette couche ne sait RIEN des MCP servers — elle prend juste un `tool_executor`
qui renvoie un string pour chaque (name, arguments). Le wiring concret avec
`jarvis_tools.Toolbox` se fait côté orchestrator (qui dépend des deux services).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from jarvis_llm.clients.ollama_client import OllamaClient, OllamaToolCall

ToolExecutor = Callable[[str, dict], str]
"""Signature : (tool_name, arguments) -> string à renvoyer au modèle.

Le caller est libre d'encoder erreurs / JSON / texte brut dans la valeur de
retour. Le LLM la verra comme un `role: tool` dans l'historique.
"""

DEFAULT_MAX_ITERATIONS = 5


@dataclass(frozen=True, slots=True)
class ToolLoopStep:
    """Trace d'une itération (utile pour debug / observability)."""

    tool_calls: tuple[OllamaToolCall, ...]
    tool_results: tuple[str, ...]  # même longueur que tool_calls, dans l'ordre


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    """Résultat final de la boucle."""

    final_text: str
    model: str
    iterations: int
    steps: tuple[ToolLoopStep, ...]
    hit_max_iterations: bool = False


async def run_tool_loop(
    client: OllamaClient,
    messages: list[dict],
    *,
    tools: list[dict],
    tool_executor: ToolExecutor,
    max_tokens: int = 1024,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> ToolLoopResult:
    """Lance le LLM avec tools, exécute les tool calls, boucle jusqu'à réponse finale.

    Args:
        client: OllamaClient initialisé.
        messages: historique initial (system + user + …).
        tools: liste de schémas d'outils Ollama-compatibles
            ([{"type": "function", "function": {"name": "...", "description": "...",
               "parameters": {...}}}, …]).
        tool_executor: fonction sync `(name, args) -> str` qui exécute l'outil.
        max_tokens: budget tokens par tour.
        max_iterations: nb max d'aller-retours LLM↔tool avant arrêt forcé.

    Returns:
        ToolLoopResult avec le texte final + trace des étapes.
    """
    working = list(messages)
    steps: list[ToolLoopStep] = []
    last_model = client.model

    for iteration in range(1, max_iterations + 1):
        completion = await client.chat(working, max_tokens=max_tokens, tools=tools)
        last_model = completion.model

        if not completion.tool_calls:
            # Pas de tool call → réponse finale
            return ToolLoopResult(
                final_text=completion.text,
                model=last_model,
                iterations=iteration,
                steps=tuple(steps),
                hit_max_iterations=False,
            )

        # Le modèle demande des tools. Ajoute la message assistant + résultats.
        assistant_msg: dict = {
            "role": "assistant",
            "content": completion.text or "",
            "tool_calls": [
                {"function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in completion.tool_calls
            ],
        }
        working.append(assistant_msg)

        results: list[str] = []
        for tc in completion.tool_calls:
            try:
                result_text = tool_executor(tc.name, tc.arguments)
            except Exception as exc:
                result_text = f"[tool-error] {type(exc).__name__}: {exc}"
            results.append(result_text)
            working.append({"role": "tool", "name": tc.name, "content": result_text})

        steps.append(
            ToolLoopStep(
                tool_calls=completion.tool_calls,
                tool_results=tuple(results),
            )
        )

    # Max iterations atteint → on demande une dernière fois SANS tools pour forcer une réponse
    completion = await client.chat(working, max_tokens=max_tokens)
    return ToolLoopResult(
        final_text=completion.text or "[boucle d'outils interrompue après max_iterations]",
        model=completion.model or last_model,
        iterations=max_iterations,
        steps=tuple(steps),
        hit_max_iterations=True,
    )


def descriptors_to_ollama_tools(descriptors) -> list[dict]:
    """Convertit une liste de `ToolDescriptor` (jarvis-tools) en schémas Ollama.

    On accepte n'importe quelle séquence d'objets ayant `.qualified_name`, `.tool.name`,
    `.tool.description`, `.tool.input_schema` — c'est pour éviter une dépendance dure
    jarvis-llm → jarvis-tools.
    """
    out: list[dict] = []
    for d in descriptors:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": d.qualified_name.replace(".", "_"),  # Ollama n'aime pas les '.'
                    "description": d.tool.description or "",
                    "parameters": d.tool.input_schema or {"type": "object", "properties": {}},
                },
            }
        )
    return out
