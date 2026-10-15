"""Backend pygame: renderiza em 2x (anti-aliasing), soma brilho em duas escalas, vinheta de emoção e rastro."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pygame

from ..core.easing import clamp
from ..effects.particles import Particle
from ..model.params import EyeParams
from .bounds import drawn_bounds
from .shapes import Layout, draw_eyes

RGB = Tuple[int, int, int]
GLOW_BLEND = 0.1   # largura (fração da tela) da transição entre o halo esquerdo e o direito
TINT_STRENGTH = 0.16  # intensidade máxima da vinheta colorida atrás dos olhos
TRAIL_START = 0.012   # velocidade (fração da largura por frame) a partir da qual o rastro aparece
TRAIL_FULL = 0.05     # velocidade em que o rastro chega ao máximo
TRAIL_JUMP = 0.12     # acima disso é um salto (troca de cena, redimensionar), não movimento: sem rastro
TRAIL_DECAY = 0.5     # quanto de brilho o rastro mantém a cada frame, no máximo
TRAIL_RELEASE = 0.55  # velocidade com que o rastro "solta" depois que o olho para


@dataclass(frozen=True)
class Quality:
    """Custo x beleza: displays pequenos (ex.: ST7789) usam níveis mais baixos."""

    supersample: int
    # (divisor do downscale, intensidade) de cada camada de brilho; a última recebe a vinheta.
    bloom: Tuple[Tuple[int, float], ...]
    trail: bool
    tint: bool


QUALITIES: Dict[str, Quality] = {
    "low": Quality(supersample=1, bloom=((10, 0.45),), trail=False, tint=False),
    "medium": Quality(supersample=2, bloom=((10, 0.45),), trail=False, tint=True),
    "high": Quality(supersample=2, bloom=((6, 0.32), (20, 0.30)), trail=True, tint=True),
}
QUALITY_ORDER = ("low", "medium", "high")


class FaceRenderer:
    """Renderizador de olhos.

    Por padrão desenha, reduz e limpa só a região que tem conteúdo (`roi=True`), o que corta o custo
    por frame sem mudar o resultado. `render` devolve uma cópia; com `reuse=True` devolve a superfície
    interna (mais rápido), válida só até o próximo `render`.
    """

    def __init__(self, width: int, height: int, bg: RGB = (4, 6, 8), quality: str = "high", roi: bool = True):
        self.bg = bg
        self.roi = roi
        self._trail_decay = 0.0
        self._last_pos: Optional[List[Tuple[float, float]]] = None
        self._vignettes: Dict[Tuple[int, int], pygame.Surface] = {}
        self.size = (max(1, width), max(1, height))
        self.set_quality(quality)

    @property
    def quality(self) -> str:
        return self._quality_name

    def set_quality(self, name: str) -> None:
        if name not in QUALITIES:
            raise ValueError(f"Qualidade desconhecida {name!r}. Disponíveis: {list(QUALITY_ORDER)}")
        self._quality_name = name
        self._q = QUALITIES[name]
        self.resize(*self.size)

    def resize(self, width: int, height: int) -> None:
        self.size = (max(1, width), max(1, height))
        ss = self._q.supersample
        self.layout = Layout(*self.size).scaled(ss)
        # Dois quadros "base" (fundo + olhos, sem halo) alternam a cada frame: o anterior serve de rastro.
        self._bases = [pygame.Surface(self.size, 0, 32), pygame.Surface(self.size, 0, 32)]
        for base in self._bases:
            base.fill(self.bg)
        self._content: List[Optional[pygame.Rect]] = [None, None]  # região suja de cada base
        self._flip = 0
        self._hires = pygame.Surface((self.layout.width, self.layout.height), 0, 32) if ss > 1 else None
        self._out = pygame.Surface(self.size, 0, 32)
        self._last_pos = None
        self._trail_decay = 0.0
        self._vignettes.clear()

    def render(self, eyes: Sequence[EyeParams], particles: Iterable[Particle] = (), reuse: bool = False) -> pygame.Surface:
        """Devolve um Surface (width x height) com os dois olhos e as partículas de emoção."""
        particles = list(particles)
        ss = self._q.supersample
        full = pygame.Rect(0, 0, *self.size)
        roi = self._region(eyes, particles) if self.roi else full

        cur, prev = self._bases[self._flip], self._bases[1 - self._flip]
        dirty = self._content[self._flip]
        if dirty is not None:
            cur.fill(self.bg, dirty)  # limpa o que esta base guardava de dois frames atrás
        if ss > 1:
            area = pygame.Rect(roi.x * ss, roi.y * ss, roi.w * ss, roi.h * ss)
            draw_eyes(self._hires, eyes, self.layout, self.bg, particles, area)
            pygame.transform.smoothscale(self._hires.subsurface(area), roi.size, cur.subsurface(roi))
        else:
            draw_eyes(cur, eyes, self.layout, self.bg, particles, roi)

        content = roi
        if self._q.trail:
            content = self._apply_trail(cur, prev, self._content[1 - self._flip], roi, eyes)
        self._content[self._flip] = content

        glows = [clamp(e.glow) for e in eyes]
        tint = self._tint_color(eyes, glows) if self._q.tint else None
        halo = self._bloom(cur, glows, tint)
        if halo is not None:
            # base + halo = halo + base: amplia o halo direto no buffer de saída e soma a base por cima.
            pygame.transform.smoothscale(halo, self.size, self._out)
            self._out.blit(cur, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        else:
            self._out.blit(cur, (0, 0))
        self._flip = 1 - self._flip
        return self._out if reuse else self._out.copy()

    def _region(self, eyes: Sequence[EyeParams], particles: Sequence[Particle]) -> pygame.Rect:
        """Região (em pixels do quadro final) que o desenho toca, alinhada ao supersampling."""
        ss = self._q.supersample
        hi = drawn_bounds(eyes, self.layout, particles)
        x0, y0 = hi.left // ss, hi.top // ss
        x1, y1 = -(-hi.right // ss), -(-hi.bottom // ss)
        return pygame.Rect(x0, y0, max(1, x1 - x0), max(1, y1 - y0)).clip(pygame.Rect(0, 0, *self.size))

    # --- brilho e vinheta ----------------------------------------------------

    def _bloom(self, frame: pygame.Surface, glows: Sequence[float], tint: Optional[RGB]) -> Optional[pygame.Surface]:
        """Halo em camadas: cada uma é uma versão borrada (reduzida) do quadro, escalada por olho.

        As reduções são encadeadas (quadro -> camada fina -> camada larga) e as camadas são somadas na
        menor resolução que as comporta. Devolve o halo nessa resolução (a ampliação fica com `render`).
        """
        if not glows or (max(glows) <= 0.01 and tint is None):
            return None
        source = frame
        layers: List[pygame.Surface] = []
        last = len(self._q.bloom) - 1
        for index, (divisor, strength) in enumerate(self._q.bloom):
            size = (max(1, self.size[0] // divisor), max(1, self.size[1] // divisor))
            raw = pygame.transform.smoothscale(source, size)
            layer = raw.copy() if index < last else raw
            layer.blit(self._glow_levels(glows, size, strength), (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            if tint is not None and index == last:
                layer.blit(self._vignette(size, tint), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            layers.append(layer)
            source = raw
        halo = layers[-1]
        for finer in reversed(layers[:-1]):
            finer.blit(pygame.transform.smoothscale(halo, finer.get_size()), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            halo = finer
        return halo

    @staticmethod
    def _glow_levels(glows: Sequence[float], size: Tuple[int, int], strength: float) -> pygame.Surface:
        """Mapa de intensidade do halo: cada metade da tela segue o brilho do seu olho."""
        left, right = (round(255 * g * strength) for g in (glows[0], glows[-1]))
        surface = pygame.Surface(size, 0, 32)
        width, height = size
        # Só a faixa de transição (GLOW_BLEND da largura, no centro) tem valores intermediários:
        # o resto é um preenchimento liso de cada lado.
        ramp = [x for x in range(width) if 0.0 < clamp(((x + 0.5) / width - 0.5) / GLOW_BLEND + 0.5) < 1.0]
        first, last = (ramp[0], ramp[-1] + 1) if ramp else (width // 2, width // 2)
        surface.fill((left, left, left), (0, 0, first, height))
        surface.fill((right, right, right), (last, 0, width - last, height))
        for x in ramp:
            t = clamp(((x + 0.5) / width - 0.5) / GLOW_BLEND + 0.5)
            level = round(left + (right - left) * t)
            pygame.draw.line(surface, (level, level, level), (x, 0), (x, height - 1))
        return surface

    @staticmethod
    def _tint_color(eyes: Sequence[EyeParams], glows: Sequence[float]) -> RGB:
        """Cor da vinheta: média das cores dos olhos, mais forte quando o brilho é alto."""
        level = TINT_STRENGTH * (0.45 + 0.55 * sum(glows) / max(len(glows), 1))
        count = max(len(eyes), 1)
        return tuple(  # type: ignore[return-value]
            round(clamp(sum(e.color[i] for e in eyes) / count / 255.0) * 255 * level) for i in range(3)
        )

    def _vignette(self, size: Tuple[int, int], color: RGB) -> pygame.Surface:
        """Mancha radial colorida centrada nos olhos (o gradiente cinza é cacheado por tamanho)."""
        base = self._vignettes.get(size)
        if base is None:
            base = pygame.Surface(size, 0, 32)
            w, h = size
            for y in range(h):
                for x in range(w):
                    dx, dy = ((x + 0.5) / w - 0.5) / 0.5, ((y + 0.5) / h - 0.5) / 0.5
                    v = clamp(1.0 - (dx * dx * 0.55 + dy * dy * 1.1))
                    level = round(255 * v * v)
                    base.set_at((x, y), (level, level, level))
            self._vignettes[size] = base
        tinted = base.copy()
        tinted.fill((*color, 255), special_flags=pygame.BLEND_RGB_MULT)
        return tinted

    # --- rastro --------------------------------------------------------------

    def _apply_trail(
        self, cur: pygame.Surface, prev: pygame.Surface, prev_content: Optional[pygame.Rect],
        roi: pygame.Rect, eyes: Sequence[EyeParams],
    ) -> pygame.Rect:
        """Persistência estilo LED: só aparece quando o olhar se move rápido.

        `prev` é o quadro anterior (já com o rastro dele). Devolve a região que `cur` passou a ocupar.
        """
        positions = [self.layout.eye_center(e, side) for side, e in zip((-1, 1), eyes)]
        speed = 0.0
        if self._last_pos is not None and len(self._last_pos) == len(positions):
            moved = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(positions, self._last_pos))
            speed = moved / self._q.supersample / max(self.size[0], 1)
        self._last_pos = positions

        target = TRAIL_DECAY * clamp((speed - TRAIL_START) / (TRAIL_FULL - TRAIL_START))
        if speed > TRAIL_JUMP:
            target, self._trail_decay = 0.0, 0.0
        self._trail_decay = max(target, self._trail_decay * TRAIL_RELEASE)
        if prev_content is None or self._trail_decay <= 0.02:
            return roi
        # Fora dessa região os dois quadros são fundo liso, e fundo * fator < fundo não muda o MAX.
        region = roi.union(prev_content)
        ghost = prev.subsurface(region).copy()
        level = round(255 * self._trail_decay)
        ghost.fill((level, level, level), special_flags=pygame.BLEND_RGB_MULT)
        cur.blit(ghost, region.topleft, special_flags=pygame.BLEND_RGB_MAX)
        return region
