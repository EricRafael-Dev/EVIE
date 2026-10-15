"""Região do quadro que o desenho realmente toca (olhos, blush e partículas).

O renderer usa isso para desenhar, reduzir e limpar só essa região em vez da tela inteira: o resto
é fundo liso. Os limites são conservadores (sempre cobrem o que `shapes.py`/`fx.py` desenham), e o
teste `test_roi.py` confere que a saída é idêntica à do desenho de tela cheia.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence

import pygame

from ..core.easing import clamp
from ..effects.particles import Particle
from ..model.params import EyeParams
from .sprites import soft_ellipse

EYE_PAD = 4  # folga em volta do retângulo do olho (anti-aliasing, polígonos de pálpebra com 1 px de sobra)


def _particle_box(p: Particle, layout) -> pygame.Rect:
    """Caixa que cobre a partícula `p` (tamanhos como nos desenhistas de `fx.py`)."""
    cx, cy = p.x * layout.width, p.y * layout.height
    unit = layout.eye_h
    if p.kind == "ring":
        rx = (p.size_x if p.size_x is not None else p.size) * layout.eye_w * 1.45 + 6
        ry = p.size * layout.eye_h * 1.45 + 6
    else:
        rx = ry = 2.5 * p.size * unit + 10
    return pygame.Rect(round(cx - rx), round(cy - ry), round(2 * rx), round(2 * ry))


def drawn_bounds(eyes: Sequence[EyeParams], layout, particles: Iterable[Particle] = ()) -> pygame.Rect:
    """Retângulo (nas coordenadas de `layout`) que contém tudo o que `draw_eyes` pinta."""
    boxes: List[pygame.Rect] = []
    lid_zones: List[pygame.Rect] = []
    for side, p in zip((-1, 1), eyes):
        w = max(p.w * layout.eye_w, 2)
        h = max(p.h * layout.eye_h, 2)
        cx = layout.width / 2 + side * layout.spacing / 2 + p.x * layout.travel_x
        cy = layout.height / 2 + p.y * layout.travel_y
        rect = pygame.Rect(0, 0, round(w), round(h))
        rect.center = (round(cx), round(cy))
        boxes.append(rect.inflate(2 * EYE_PAD, 2 * EYE_PAD))

        if clamp(p.blush) >= 0.02:
            bx, by = layout.eye_center(p, side)
            sw, sh = soft_ellipse(0.7 * layout.eye_w, 0.22 * layout.eye_h, 0.7).get_size()
            blush = pygame.Rect(0, 0, sw, sh)
            blush.center = (round(bx + side * 0.1 * layout.eye_w), round(by + 0.42 * layout.eye_h))
            boxes.append(blush.inflate(4, 4))

        bottom_cover = clamp(p.lid_bottom) * rect.h
        if bottom_cover > 0.5:  # a tampa de baixo repinta o fundo abaixo do olho
            boxes.append(pygame.Rect(rect.left - 1, round(rect.bottom - bottom_cover), rect.w + 2, round(bottom_cover + rect.h)))

        top_cover = clamp(p.lid_top) * rect.h
        tilt = p.lid_tilt * 0.5 * rect.h
        if top_cover > 0.5 or abs(tilt) > 0.5:
            # O polígono da pálpebra vai de rect.top - h até as bordas inclinadas (que podem passar do retângulo).
            lowest = max(rect.top + top_cover + tilt, rect.top + top_cover - tilt)
            if lowest > rect.bottom:
                boxes.append(pygame.Rect(rect.left - 1, rect.bottom, rect.w + 2, int(lowest - rect.bottom) + 2))
            # Acima do olho é fundo sobre fundo: só importa se houver algo atrás (anéis), checado abaixo.
            lid_zones.append(pygame.Rect(rect.left - 1, rect.top - rect.h, rect.w + 2, rect.h))

    back: List[pygame.Rect] = []
    for particle in particles:
        box = _particle_box(particle, layout)
        boxes.append(box)
        if particle.layer == "back":
            back.append(box)
    # Fundo sobre fundo não muda nada: a zona da pálpebra só importa se houver algo atrás dela (anéis).
    for zone in lid_zones:
        if zone.collidelist(back) != -1:
            boxes.append(zone)

    area = boxes[0].unionall(boxes[1:])
    return area.clip(pygame.Rect(0, 0, layout.width, layout.height))
