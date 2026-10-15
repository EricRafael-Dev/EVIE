from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandEnvelope:
    """Envelope de Contexto por Dispositivo para roteamento seguro de comandos e áudio."""
    source_device_id: str      # ex: "desktop-main", "poco-x7", "tablet-pad7", "brave-ext"
    input_modality: str        # "voice" | "text" | "vision" | "clipper"
    reply_audio_target: str    # "pc" | "origin_ws" | "silent"
    payload: Any

    def to_prompt_prefix(self) -> str:
        """Gera o prefixo de injeção contextual para o modelo."""
        return f"[DEVICE_CONTEXT: origin={self.source_device_id} | modality={self.input_modality}]"
