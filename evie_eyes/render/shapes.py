"""Desenho procedural de um olho com pygame (sem sprites de imagem)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Tuple

import pygame

from ..core.easing import clamp
from ..effects.particles import Particle
from ..model import geometry
from ..model.params import EyeParams
from .cache import LruCache, blit_tinted
from .fx import draw_particles
from .glyphs import draw_glyph
from .sprites import blit_soft

RGB = Tuple[int, int, int]
WHITE: RGB = (255, 255, 255)
CORE_MIN = 4  # espessura mínima (px) do miolo do chevron, antes de engordar com o pincel redondo
CHEVRON_HEIGHT = 0.7  # altura do ^ em relação à altura do olho
CHEVRON_STROKE = 0.2  # espessura do traço em relação à altura do olho
SHADE_ROWS = 64
_SHADE_CACHE: Dict[int, pygame.Surface] = {}
HIGHLIGHT_OPACITY = 0.72    # opacidade máxima do reflexo (translúcido, deixa a cor do olho aparecer)
HIGHLIGHT_SOFTNESS = 0.45   # quanto da borda do reflexo é esfumaçada
HIGHLIGHT_PARALLAX = 0.08   # deslocamento do reflexo contra o olhar (fração do olho)
HIGHLIGHT_WET_SCALE = 0.3   # reflexo cresce até 30% com o olho marejado
# Manchas do reflexo: (centro x, centro y) relativos ao olho, (largura, altura) relativas ao menor lado.
HIGHLIGHT_SPOTS = ((0.30, 0.27, 0.22, 0.26), (0.47, 0.45, 0.09, 0.09))
# Nos símbolos o reflexo precisa ficar dentro da forma (o canto do retângulo é vazio).
GLYPH_HIGHLIGHT_SPOTS = {
    "heart": ((0.30, 0.31, 0.19, 0.21), (0.43, 0.43, 0.08, 0.08)),
    "star": ((0.42, 0.40, 0.15, 0.17), (0.50, 0.52, 0.07, 0.07)),
}
GLYPH_MIN_H = 0.3  # abaixo dessa altura (piscando) o símbolo vira a linha fina de olho fechado
WATERLINE_OPACITY = 0.45
BLUSH_COLOR: RGB = (255, 110, 160)
BLUSH_OPACITY = 0.75


@dataclass(frozen=True)
class Layout:
    """Geometria base em pixels; os parâmetros dos olhos são relativos a ela."""

    width: int
    height: int

    @property
    def eye_w(self) -> float:
        return self.width * geometry.EYE_W

    @property
    def eye_h(self) -> float:
        return self.height * geometry.EYE_H

    @property
    def spacing(self) -> float:
        """Distância entre os centros dos olhos."""
        return self.width * geometry.SPACING

    @property
    def travel_x(self) -> float:
        return self.width * geometry.TRAVEL_X

    @property
    def travel_y(self) -> float:
        return self.height * geometry.TRAVEL_Y

    def eye_center(self, p: EyeParams, side: int) -> Tuple[float, float]:
        nx, ny = geometry.eye_center(p, side)
        return nx * self.width, ny * self.height

    def scaled(self, factor: int) -> "Layout":
        return Layout(self.width * factor, self.height * factor)


def _arc_mask(rect: pygame.Rect, arc: float, radius: int) -> pygame.Surface:
    """Máscara (branca com alfa) do olho feliz (^): dois traços retos que se encontram no topo.

    Com arc = 0 é o retângulo arredondado normal; com arc = 1, um chevron de espessura uniforme.
    Constrói o miolo (forma "encolhida" em r) e o engorda de volta com círculos de raio r
    ao longo do contorno, o que arredonda todas as pontas.
    """
    thickness = CHEVRON_STROKE * rect.h
    r = (1.0 - arc) * radius + arc * max(0.0, (thickness - CORE_MIN) / 2.0)
    core_t = max(float(CORE_MIN), thickness - 2.0 * r)
    margin = round(r)
    inset = pygame.Rect(margin, margin, max(2, rect.w - 2 * margin), max(2, rect.h - 2 * margin))

    core = pygame.Surface(rect.size, pygame.SRCALPHA)
    clear = (0, 0, 0, 0)
    pygame.draw.rect(core, (255, 255, 255, 255), inset)

    # Coordenadas simétricas em torno do centro dos pixels, para as duas pontas ficarem iguais.
    mid = inset.left + (inset.w - 1) / 2.0
    half_w = (inset.w - 1) / 2.0
    top = inset.top
    span_h = inset.h - 1
    bottom = inset.bottom - 1

    # O chevron ocupa só parte da altura e fica centralizado no retângulo do olho.
    squash = arc * (1.0 - CHEVRON_HEIGHT) * span_h / 2.0
    apex_y = top + squash
    foot_y = bottom - squash
    rise = max(1.0, foot_y - apex_y)
    edge_y = round(apex_y + arc * rise)
    pygame.draw.polygon(core, clear, [
        (inset.left - 1, -1),
        (inset.right + 1, -1),
        (inset.right + 1, edge_y),
        (round(mid), round(apex_y)),
        (inset.left - 1, edge_y),
    ])
    pygame.draw.rect(core, clear, (0, round(foot_y) + 1, rect.w, rect.h))

    # Deslocamentos da borda interna para uma espessura perpendicular `core_t`.
    slant = math.hypot(half_w, rise)
    offset_x = core_t * slant / rise
    offset_y = core_t * slant / max(1.0, half_w)
    hole_hw = max(1.0, half_w * 1.05 - arc * (half_w * 0.05 + offset_x))
    hole_apex = foot_y - arc * max(0.0, rise - offset_y)
    pygame.draw.polygon(core, clear, [
        (round(mid - hole_hw), round(foot_y) + 1),
        (round(mid), round(hole_apex)),
        (round(mid + hole_hw), round(foot_y) + 1),
    ])

    shape = pygame.Surface(rect.size, pygame.SRCALPHA)
    core_mask = pygame.mask.from_surface(core)
    brush = round(r)
    if brush >= 1:
        for part in core_mask.connected_components():
            for point in part.outline(3):
                pygame.draw.circle(shape, (255, 255, 255, 255), point, brush)
    shape.blit(core_mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=clear), (0, 0))
    return shape


_BODIES = LruCache(32)


def _draw_body(surface: pygame.Surface, rect: pygame.Rect, color: RGB, radius: int) -> None:
    """Corpo do olho: retângulo arredondado. Desenhá-lo é caro em resoluções altas, então vem de uma máscara."""
    if rect.w * rect.h < 4096:  # olhos minúsculos (piscando): desenhar direto sai mais barato
        pygame.draw.rect(surface, color, rect, border_radius=radius)
        return

    def build() -> pygame.Surface:
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255), mask.get_rect(), border_radius=radius)
        return mask

    blit_tinted(surface, _BODIES.get((rect.w, rect.h, radius), build), rect.topleft, color)


_ARC_MASKS = LruCache(32)
_GLYPH_MASKS = LruCache(48)
_RAMPS = LruCache(32)
GLYPH_MASK_PAD = 2  # o arredondamento do símbolo pode passar 1 px do retângulo


def _draw_arc_eye(surface: pygame.Surface, rect: pygame.Rect, color: RGB, arc: float, radius: int) -> None:
    """Desenha o `^`. A forma só depende do tamanho, então a máscara é reaproveitada entre frames."""
    mask = _ARC_MASKS.get((rect.w, rect.h, round(arc, 5), radius), lambda: _arc_mask(rect, arc, radius))
    blit_tinted(surface, mask, rect.topleft, color)


def _draw_glyph_cached(surface: pygame.Surface, rect: pygame.Rect, color: RGB, glyph: str) -> None:
    def build() -> pygame.Surface:
        mask = pygame.Surface((rect.w + 2 * GLYPH_MASK_PAD, rect.h + 2 * GLYPH_MASK_PAD), pygame.SRCALPHA)
        draw_glyph(mask, pygame.Rect(GLYPH_MASK_PAD, GLYPH_MASK_PAD, rect.w, rect.h), (255, 255, 255), glyph)
        return mask

    mask = _GLYPH_MASKS.get((glyph, rect.w, rect.h), build)
    blit_tinted(surface, mask, (rect.left - GLYPH_MASK_PAD, rect.top - GLYPH_MASK_PAD), color)


def _shade_column(shade: float) -> pygame.Surface:
    """Coluna 1xN com o multiplicador vertical: topo intacto, base escurecida."""
    key = round(clamp(shade) * 100)
    column = _SHADE_CACHE.get(key)
    if column is None:
        column = pygame.Surface((1, SHADE_ROWS), 0, 32)
        for row in range(SHADE_ROWS):
            t = row / (SHADE_ROWS - 1)
            level = round(255 * (1.0 - key / 100 * t ** 1.6))
            column.set_at((0, row), (level, level, level))
        _SHADE_CACHE[key] = column
    return column


def _shade(surface: pygame.Surface, rect: pygame.Rect, shade: float) -> None:
    """Gradiente de volume: multiplica o olho por uma rampa vertical (fundo escuro quase não muda)."""
    if shade <= 0.005 or rect.w < 2 or rect.h < 2:
        return
    key = round(clamp(shade) * 100)
    ramp = _RAMPS.get((key, rect.w, rect.h), lambda: pygame.transform.scale(_shade_column(shade), rect.size))
    surface.blit(ramp, rect.topleft, special_flags=pygame.BLEND_RGB_MULT)


def _draw_highlight(
    surface: pygame.Surface,
    rect: pygame.Rect,
    p: EyeParams,
    lid: Tuple[float, float],
    visible_bottom: float,
    spot_defs: Sequence[Tuple[float, float, float, float]] = HIGHLIGHT_SPOTS,
) -> None:
    """Reflexo especular: luz fixa no canto superior esquerdo, com leve paralaxe contra o olhar.

    `lid` = altura (y) da borda da pálpebra superior nas laterais esquerda e direita do olho;
    o reflexo desce para ficar logo abaixo dela, em vez de aparecer cortado.
    """
    openness = clamp((p.h - 0.25) / 0.35)
    strength = clamp(p.highlight) * openness * (1.0 - clamp(p.arc * 2.0))
    if strength < 0.02:
        return
    size = min(rect.w, rect.h) * (1.0 + HIGHLIGHT_WET_SCALE * clamp(p.wet))
    shift_x = -p.x * HIGHLIGHT_PARALLAX * rect.w
    shift_y = -p.y * HIGHLIGHT_PARALLAX * rect.h
    spots = []
    for fx, fy, fw, fh in spot_defs:
        spot = pygame.Rect(0, 0, max(1, round(fw * size)), max(1, round(fh * size)))
        spot.center = (round(rect.left + fx * rect.w + shift_x), round(rect.top + fy * rect.h + shift_y))
        spots.append(spot)

    def lid_y(x: float) -> float:
        u = (x - rect.left) / max(rect.w, 1)
        return lid[0] + (lid[1] - lid[0]) * u

    main = spots[0]
    pad = 0.05 * size
    drop = max(0.0, max(lid_y(main.left), lid_y(main.right)) + pad - main.top)
    room = visible_bottom - (main.bottom + drop)
    strength *= clamp(room / (0.15 * size))
    if strength < 0.02:
        return

    previous_clip = surface.get_clip()
    surface.set_clip(rect.clip(previous_clip))
    for spot in spots:
        center = (spot.centerx, spot.centery + drop)
        blit_soft(surface, center, spot.w, spot.h, WHITE, HIGHLIGHT_OPACITY * strength, HIGHLIGHT_SOFTNESS)
    surface.set_clip(previous_clip)


def _draw_waterline(surface: pygame.Surface, rect: pygame.Rect, p: EyeParams, visible_bottom: float) -> None:
    """Olho marejado: uma faixa clara e difusa logo acima da borda de baixo."""
    wet = clamp(p.wet) * clamp((p.h - 0.25) / 0.35) * (1.0 - clamp(p.arc * 2.0))
    if wet < 0.02:
        return
    previous_clip = surface.get_clip()
    surface.set_clip(rect.clip(previous_clip))
    center = (rect.centerx, visible_bottom - 0.14 * rect.h)
    blit_soft(surface, center, 0.62 * rect.w, 0.09 * rect.h, WHITE, WATERLINE_OPACITY * wet, 0.6)
    surface.set_clip(previous_clip)


def _draw_blush(surface: pygame.Surface, p: EyeParams, layout: Layout, side: int) -> None:
    """Bochecha rosada logo abaixo do olho, um pouco para fora."""
    blush = clamp(p.blush)
    if blush < 0.02:
        return
    cx, cy = layout.eye_center(p, side)
    center = (cx + side * 0.1 * layout.eye_w, cy + 0.42 * layout.eye_h)
    blit_soft(surface, center, 0.7 * layout.eye_w, 0.22 * layout.eye_h, BLUSH_COLOR, BLUSH_OPACITY * blush, 0.7)


def draw_eye(
    surface: pygame.Surface,
    p: EyeParams,
    cx: float,
    cy: float,
    layout: Layout,
    side: int,
    bg: RGB,
    min_px: int = 2,
) -> None:
    """Desenha um olho. `side` = -1 (esquerdo) ou +1 (direito); o canto interno fica virado para o centro."""
    w = max(p.w * layout.eye_w, min_px)
    h = max(p.h * layout.eye_h, min_px)
    cx += p.x * layout.travel_x
    cy += p.y * layout.travel_y

    rect = pygame.Rect(0, 0, round(w), round(h))
    rect.center = (round(cx), round(cy))
    color = tuple(int(clamp(c, 0, 255)) for c in p.color)
    radius = int(clamp(p.radius) * min(rect.w, rect.h) / 2)
    arc = clamp(p.arc)
    # Fechado (piscando), o símbolo vira a linha fina do olho comum.
    glyph = p.glyph if p.glyph and p.h > GLYPH_MIN_H else ""
    if glyph:
        _draw_glyph_cached(surface, rect, color, glyph)
    elif arc > 0.01:
        _draw_arc_eye(surface, rect, color, arc, radius)
    else:
        _draw_body(surface, rect, color, radius)
    # No ^ o traço é fino: gradiente forte deixaria as pontas apagadas.
    _shade(surface, rect, p.shade * (1.0 - 0.7 * arc))

    # Com arc > 0.01 (olhos felizes em ^), pálpebras de tédio/sono NUNCA devem cortar o arco pela metade
    if arc > 0.01:
        top_cover = 0.0
        tilt = 0.0
        bottom_cover = 0.0
    else:
        top_cover = clamp(p.lid_top) * rect.h
        tilt = p.lid_tilt * 0.5 * rect.h
        bottom_cover = clamp(p.lid_bottom) * rect.h

    margin = rect.h
    inner = rect.top + top_cover + tilt   # canto voltado para o centro
    outer = rect.top + top_cover - tilt
    # Olho esquerdo (side < 0): o canto interno é o direito.
    y_left, y_right = (outer, inner) if side < 0 else (inner, outer)
    visible_bottom = rect.bottom - bottom_cover
    _draw_waterline(surface, rect, p, visible_bottom)
    _draw_highlight(surface, rect, p, (y_left, y_right), visible_bottom, GLYPH_HIGHLIGHT_SPOTS.get(glyph, HIGHLIGHT_SPOTS))

    if top_cover > 0.5 or abs(tilt) > 0.5:
        pygame.draw.polygon(surface, bg, [
            (rect.left - 1, rect.top - margin),
            (rect.right + 1, rect.top - margin),
            (rect.right + 1, y_right),
            (rect.left - 1, y_left),
        ])

    if bottom_cover > 0.5:
        y = rect.bottom - bottom_cover
        pygame.draw.rect(surface, bg, (rect.left - 1, round(y), rect.w + 2, round(bottom_cover + margin)))


def draw_eyes(
    surface: pygame.Surface,
    eyes: Sequence[EyeParams],
    layout: Layout,
    bg: RGB,
    particles: Iterable[Particle] = (),
    area: Optional[pygame.Rect] = None,
) -> None:
    """Desenha os dois olhos e as partículas. Com `area`, pinta (e limpa) só essa região da superfície."""
    particles = list(particles)
    if area is None:
        surface.fill(bg)
    else:
        surface.set_clip(area)
        surface.fill(bg, area)
    draw_particles(surface, particles, layout, "back")
    # Blush fica atrás dos olhos: só a parte de baixo aparece, como uma bochecha.
    for side, params in zip((-1, 1), eyes):
        _draw_blush(surface, params, layout, side)
    cy = layout.height / 2
    for side, params in zip((-1, 1), eyes):
        cx = layout.width / 2 + side * layout.spacing / 2
        draw_eye(surface, params, cx, cy, layout, side, bg)
    draw_particles(surface, particles, layout, "front")
    if area is not None:
        surface.set_clip(None)
