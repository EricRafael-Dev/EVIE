"""Proporções do rosto, em frações da tela (independentes de resolução).

Usadas pelo renderer (pixels) e pelos efeitos (que guardam posições normalizadas 0..1).
"""
from __future__ import annotations

from typing import Tuple

from .params import EyeParams

EYE_W = 0.22     # largura base do olho / largura da tela
EYE_H = 0.36     # altura base do olho / altura da tela
SPACING = 0.38   # distância entre os centros dos olhos / largura da tela
TRAVEL_X = 0.12  # deslocamento máximo do olhar / largura da tela
TRAVEL_Y = 0.15  # deslocamento máximo do olhar / altura da tela


def eye_center(p: EyeParams, side: int) -> Tuple[float, float]:
    """Centro do olho em coordenadas normalizadas (x: fração da largura, y: fração da altura)."""
    return 0.5 + side * SPACING / 2.0 + p.x * TRAVEL_X, 0.5 + p.y * TRAVEL_Y
