from __future__ import annotations

from agent_memory.tools import MemoryToolManager


def search_second_brain_handler(parameters: dict, player=None, **_) -> str:
    """Executa busca profunda no Segundo Cérebro (Obsidian Markdown)."""
    query = str(parameters.get("query", "")).strip()
    include_linked = bool(parameters.get("include_linked", True))

    if not query:
        return "Por favor, informe os termos de busca para pesquisar no Segundo Cérebro."

    mgr = MemoryToolManager()
    res = mgr.search_second_brain(query=query, include_linked=include_linked)
    
    if player and hasattr(player, "show_content"):
        try:
            player.show_content(f"SEGUNDO CÉREBRO — {query[:30]}", res)
        except Exception:
            pass

    return res


TOOL = {
    "name": "search_second_brain",
    "description": "Pesquisa notas, dados históricos, projetos e preferências no Segundo Cérebro (Obsidian) com busca textual FTS5 BM25 e expansão automática de grafo de 1 salto via WikiLinks [[...]].",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Termos ou assunto a pesquisar nas notas do Segundo Cérebro.",
            },
            "include_linked": {
                "type": "BOOLEAN",
                "description": "Se verdadeiro, traz o resumo das notas linkadas via WikiLinks (grafo de 1 salto). Padrão é true.",
            },
        },
        "required": ["query"],
    },
    "handler": search_second_brain_handler,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}
