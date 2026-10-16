"""Desenho das partículas de emoção: lágrima, Zzz, brilho ✦, marca de raiva 💢, onda de choque e "!"."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Sequence, Tuple

import pygame

try:
    from evie_eyes.core.easing import clamp, ease_out_back, ease_out_cubic
    from evie_eyes.effects.particles import Particle, heartbeat
    from evie_eyes.render.glyphs import draw_glyph
except ImportError:
    from ..core.easing import clamp, ease_out_back, ease_out_cubic
    from ..effects.particles import Particle, heartbeat
    from .glyphs import draw_glyph

if TYPE_CHECKING:
    try:
        from evie_eyes.render.shapes import Layout
    except ImportError:
        from .shapes import Layout

RGB = Tuple[int, int, int]
Point = Tuple[float, float]


def _rgb(color: Sequence[float]) -> RGB:
    return (int(clamp(color[0], 0, 255)), int(clamp(color[1], 0, 255)), int(clamp(color[2], 0, 255)))


def _blit_canvas(surface: pygame.Surface, canvas: pygame.Surface, center: Point, alpha: float) -> None:
    a = round(255 * clamp(alpha))
    if a <= 0:
        return
    if a < 255:
        # Em superfícies com per-pixel alpha (SRCALPHA), set_alpha() causa um retângulo escuro no SDL.
        # BLEND_RGBA_MULT modula apenas os pixels coloridos visíveis, mantendo o fundo 100% transparente.
        canvas = canvas.copy()
        canvas.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(canvas, canvas.get_rect(center=(round(center[0]), round(center[1]))))


def _round_polyline(canvas: pygame.Surface, color: RGB, points: List[Point], width: int) -> None:
    """Linha grossa com juntas e pontas arredondadas."""
    pygame.draw.lines(canvas, color, False, points, width)
    for point in points:
        pygame.draw.circle(canvas, color, point, width / 2)


def _rotate(points: Iterable[Point], angle: float) -> List[Point]:
    c, s = math.cos(angle), math.sin(angle)
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def _tear(surface: pygame.Surface, p: Particle, center: Point, unit: float) -> None:
    r = p.size * unit * (0.35 + 0.65 * p.grow)
    if r < 1.0:
        return
    pad = 2
    canvas = pygame.Surface((round(2 * r) + 2 * pad, round(3.4 * r) + 2 * pad), pygame.SRCALPHA)
    cx, cy = r + pad, 2.4 * r + pad
    color = _rgb(p.color)
    pygame.draw.circle(canvas, color, (cx, cy), r)
    pygame.draw.polygon(canvas, color, [(cx - 0.92 * r, cy - 0.38 * r), (cx, cy - 2.3 * r), (cx + 0.92 * r, cy - 0.38 * r)])
    pygame.draw.circle(canvas, (255, 255, 255, 190), (cx - 0.35 * r, cy - 0.15 * r), max(1.0, 0.3 * r))
    # O centro do círculo da gota (0.7r abaixo do centro do canvas) fica na posição da partícula.
    _blit_canvas(surface, canvas, (center[0], center[1] - 0.7 * r), p.alpha)


def _zzz(surface: pygame.Surface, p: Particle, center: Point, unit: float) -> None:
    s = p.size * unit * (0.7 + 0.6 * p.progress)
    if s < 2.0:
        return
    width = max(2, round(0.2 * s))
    half = s * 0.8 + width
    shape = _rotate([(-0.5 * s, -0.5 * s), (0.5 * s, -0.5 * s), (-0.5 * s, 0.5 * s), (0.5 * s, 0.5 * s)], p.angle)
    canvas = pygame.Surface((round(2 * half), round(2 * half)), pygame.SRCALPHA)
    _round_polyline(canvas, _rgb(p.color), [(x + half, y + half) for x, y in shape], width)
    sway = math.sin(p.age * 2.5 + p.phase) * 0.25 * s
    _blit_canvas(surface, canvas, (center[0] + sway, center[1]), p.alpha)


def _sparkle(surface: pygame.Surface, p: Particle, center: Point, unit: float) -> None:
    radius = p.size * unit * math.sin(math.pi * p.progress)  # cresce e some
    if radius < 1.5:
        return
    points = []
    for k in range(8):
        a = p.angle + k * math.pi / 4.0 - math.pi / 2.0
        rad = radius if k % 2 == 0 else 0.28 * radius
        points.append((math.cos(a) * rad + radius + 2, math.sin(a) * rad + radius + 2))
    size = round(2 * radius) + 4
    canvas = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.polygon(canvas, _rgb(p.color), points)
    pygame.draw.circle(canvas, (255, 255, 255), (radius + 2, radius + 2), max(1.0, 0.18 * radius))
    _blit_canvas(surface, canvas, center, p.alpha)


# Uma "perna" da marca de raiva: curva em L com o canto virado para o centro (escala -1..1).
# O afastamento (0.38) deixa um "+" vazio entre as quatro pernas, como no símbolo 💢.
_ANGER_LEG = [
    ((1 - t) ** 2 * 0.38 + 2 * (1 - t) * t * 0.38 + t * t * 1.0, (1 - t) ** 2 * 1.0 + 2 * (1 - t) * t * 0.38 + t * t * 0.38)
    for t in (i / 10 for i in range(11))
]


def _anger(surface: pygame.Surface, p: Particle, center: Point, unit: float) -> None:
    half = 0.5 * p.size * unit * (1.0 + 0.18 * heartbeat(p.age))
    if half < 2.0:
        return
    width = max(2, round(0.36 * half))
    size = round(2 * half) + 2 * width
    canvas = pygame.Surface((size, size), pygame.SRCALPHA)
    color = _rgb(p.color)
    for quarter in range(4):
        leg = _rotate(_ANGER_LEG, quarter * math.pi / 2.0)
        _round_polyline(canvas, color, [(x * half + size / 2, y * half + size / 2) for x, y in leg], width)
    _blit_canvas(surface, canvas, center, p.alpha)


def _ring(surface: pygame.Surface, p: Particle, center: Point, unit: float, layout: Layout) -> None:
    grow = 1.0 + 0.45 * ease_out_cubic(p.progress)
    rx = (p.size_x if p.size_x is not None else p.size) * layout.eye_w * grow
    ry = p.size * layout.eye_h * grow
    width = max(1, round(0.08 * unit * (1.0 - p.progress)))
    canvas = pygame.Surface((round(2 * rx) + 4, round(2 * ry) + 4), pygame.SRCALPHA)
    pygame.draw.ellipse(canvas, _rgb(p.color), canvas.get_rect().inflate(-4, -4), width)
    _blit_canvas(surface, canvas, center, p.alpha * 0.6)


def _exclaim(surface: pygame.Surface, p: Particle, center: Point, unit: float) -> None:
    s = p.size * unit * ease_out_back(clamp(p.age / 0.25))
    if s < 3.0:
        return
    w = round(1.2 * s)
    canvas = pygame.Surface((w, w), pygame.SRCALPHA)
    color = _rgb(p.color)
    bar = pygame.Rect(0, 0, max(1, round(0.26 * s)), max(1, round(0.62 * s)))
    bar.center = (w // 2, round(w / 2 - 0.2 * s))
    pygame.draw.rect(canvas, color, bar, border_radius=bar.w // 2)
    pygame.draw.circle(canvas, color, (w / 2, w / 2 + 0.36 * s), 0.14 * s)
    canvas = pygame.transform.rotate(canvas, -math.degrees(p.angle))
    _blit_canvas(surface, canvas, center, p.alpha)


def _heart(surface: pygame.Surface, p: Particle, center: Point, unit: float) -> None:
    s = round(p.size * unit * (0.75 + 0.25 * ease_out_back(clamp(p.age / 0.3))))
    if s < 3:
        return
    canvas = pygame.Surface((s + 4, s + 4), pygame.SRCALPHA)
    draw_glyph(canvas, canvas.get_rect().inflate(-4, -4), _rgb(p.color), "heart")
    sway = math.sin(p.age * 3.0 + p.phase) * 0.18 * s
    _blit_canvas(surface, canvas, (center[0] + sway, center[1]), p.alpha)


_DRAWERS: Dict[str, Callable[..., None]] = {
    "tear": _tear,
    "zzz": _zzz,
    "sparkle": _sparkle,
    "anger": _anger,
    "exclaim": _exclaim,
    "heart": _heart,
}


def draw_particles(surface: pygame.Surface, particles: Iterable[Particle], layout: Layout, layer: str) -> None:
    """Desenha as partículas da camada `layer` ("back" atrás dos olhos, "front" na frente)."""
    unit = layout.eye_h
    for p in particles:
        if p.layer != layer or p.alpha <= 0.0:
            continue
        center = (p.x * layout.width, p.y * layout.height)
        if p.kind == "ring":
            _ring(surface, p, center, unit, layout)
            continue
        drawer = _DRAWERS.get(p.kind)
        if drawer is not None:
            drawer(surface, p, center, unit)
