from __future__ import annotations

import asyncio
from agent_memory.study_engine import StudyAndTimelineEngine


def recall_timeline_handler(parameters: dict, player=None, session_memory=None, **_) -> str:
    """Executa a síntese da linha do tempo e status de onde o usuário parou."""
    period = str(parameters.get("period", "hoje")).strip()
    engine = StudyAndTimelineEngine()

    try:
        # Executa em novo loop ou roda assíncrono
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(engine.recall_timeline(period=period))
        loop.close()
    except Exception as e:
        res = f"Erro ao recuperar linha do tempo: {e}"

    if player and hasattr(player, "show_content"):
        try:
            player.show_content(f"LINHA DO TEMPO — {period.upper()}", res)
        except Exception:
            pass

    return res


TOOL = {
    "name": "recall_timeline",
    "description": "Cruza notas modificadas no Segundo Cérebro e o histórico recente para responder 'Onde eu parei no projeto X?', 'O que fiz hoje?' ou reconstituir o foco recente.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "period": {
                "type": "STRING",
                "description": "Período temporal desejado (ex: 'hoje', 'ontem', 'essa semana', ou nome de um projeto específico).",
            },
        },
    },
    "handler": recall_timeline_handler,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}
