from __future__ import annotations

import asyncio
from agent_memory.study_engine import StudyAndTimelineEngine


def generate_study_quiz_handler(parameters: dict, player=None, **_) -> str:
    """Gera um quiz/flashcards de estudos baseado nas notas do Obsidian."""
    topic = str(parameters.get("topic", "")).strip()
    if not topic:
        return "Por favor, informe o tópico ou assunto do quiz de estudos."

    engine = StudyAndTimelineEngine()

    try:
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(engine.generate_study_quiz(topic=topic))
        loop.close()
    except Exception as e:
        res = f"Erro ao gerar quiz de estudos: {e}"

    if player and hasattr(player, "show_content"):
        try:
            player.show_content(f"QUIZ DE ESTUDOS — {topic.upper()}", res)
        except Exception:
            pass

    return res


TOOL = {
    "name": "generate_study_quiz",
    "description": "Lê notas de estudo ou conceitos no Segundo Cérebro e gera 3 perguntas rápidas com respostas em formato de flashcard para revisão ativa e fixação.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "topic": {
                "type": "STRING",
                "description": "Tema, matéria ou conceito das notas para gerar o quiz (ex: 'arquitetura do mark lv', 'cálculo', 'python').",
            },
        },
        "required": ["topic"],
    },
    "handler": generate_study_quiz_handler,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}
