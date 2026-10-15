from __future__ import annotations

from agent_memory.tools import MemoryToolManager


def read_memory_note_handler(parameters: dict, player=None, **_) -> str:
    """Lê uma nota específica do Segundo Cérebro com validação segura de caminho."""
    target_file = str(parameters.get("target_file", "")).strip()

    if not target_file:
        return "Por favor, informe o caminho do arquivo (ex: 'perfil/usuario.md')."

    mgr = MemoryToolManager()
    content = mgr.read_memory_note(target_file)

    if player and hasattr(player, "show_content") and not content.startswith("Erro"):
        try:
            player.show_content(f"NOTA: {target_file}", content[:1500])
        except Exception:
            pass

    return content


TOOL = {
    "name": "read_memory_note",
    "description": "Lê o conteúdo integral de uma nota em Markdown do Segundo Cérebro (ex: 'perfil/usuario.md', 'perfil/hardware_pc.md', 'projetos/evie.md', 'entidades/pessoas/nome.md').",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target_file": {
                "type": "STRING",
                "description": "Caminho relativo da nota dentro de second_brain/ (com ou sem extensão .md).",
            },
        },
        "required": ["target_file"],
    },
    "handler": read_memory_note_handler,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}
