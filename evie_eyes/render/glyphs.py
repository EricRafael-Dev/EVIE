"""Formas de olho em símbolo (coração, estrela), com pontas e curvas arredondadas."""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pygame

RGB = Tuple[int, int, int]
Point = Tuple[float, float]


def _normalize(points: List[Point]) -> List[Point]:
    """Ajusta a forma para caber exatamente em [-1, 1] x [-1, 1] (centrada na caixa)."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    hx, hy = (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2
    return [((x - cx) / hx, (y - cy) / hy) for x, y in points]


def _heart(samples: int = 48) -> List[Point]:
    pts = []
    for i in range(samples):
        t = 2.0 * math.pi * i / samples
        x = 16.0 * math.sin(t) ** 3
        y = -(13.0 * math.cos(t) - 5.0 * math.cos(2 * t) - 2.0 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((x, y))
    return _normalize(pts)


def _star(inner: float = 0.5) -> List[Point]:
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        r = 1.0 if k % 2 == 0 else inner
        pts.append((math.cos(a) * r, math.sin(a) * r))
    return _normalize(pts)


UNIT_SHAPES: Dict[str, List[Point]] = {"heart": _heart(), "star": _star()}
ROUNDING = {"heart": 0.05, "star": 0.08}  # raio de arredondamento (fração do menor lado)


def _densify(points: List[Point], step: float) -> List[Point]:
    """Reamostra o contorno fechado com pontos a cada `step` px (no máximo)."""
    dense: List[Point] = []
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        count = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / step))
        dense.extend((x0 + (x1 - x0) * k / count, y0 + (y1 - y0) * k / count) for k in range(count))
    return dense


def draw_glyph(surface: pygame.Surface, rect: pygame.Rect, color: RGB, glyph: str) -> None:
    """Desenha `glyph` preenchendo `rect`.

    O arredondamento vem de engordar um miolo menor com círculos de raio r ao longo do contorno
    (soma de Minkowski), o que dá curvas lisas mesmo nas pontas da estrela e no bico do coração.
    """
    unit = UNIT_SHAPES[glyph]
    r = ROUNDING[glyph] * min(rect.w, rect.h)
    hw, hh = max(1.0, rect.w / 2 - r), max(1.0, rect.h / 2 - r)
    cx, cy = rect.centerx, rect.centery
    pts = [(cx + x * hw, cy + y * hh) for x, y in unit]
    pygame.draw.polygon(surface, color, pts)
    if r >= 1.0:
        for point in _densify(pts, max(1.5, 0.6 * r)):
            pygame.draw.circle(surface, color, point, r)
