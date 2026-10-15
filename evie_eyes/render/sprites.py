"""Sprites de borda suave (reflexo, blush, linha d'água), com cache."""
from __future__ import annotations

from typing import Dict, Tuple

import pygame

from ..core.easing import clamp

RGB = Tuple[int, int, int]
QUANT = 2  # px: tamanhos são arredondados para reaproveitar o cache entre frames
_CACHE: Dict[Tuple[int, int, int], pygame.Surface] = {}
_CACHE_LIMIT = 512
TINTED_LIMIT = 96  # sprites já tingidos (cor + opacidade) que se repetem entre frames
_TINTED: Dict[Tuple[int, Tuple[int, int, int], int], pygame.Surface] = {}
BLUR_STEP = 4  # raio de blur (px) a partir do qual o sprite é borrado em resolução reduzida


def soft_ellipse(w: float, h: float, softness: float = 0.35) -> pygame.Surface:
    """Elipse branca cujo alfa cai suavemente na borda; `softness` = fração do menor lado que é borrada."""
    qw, qh = max(1, round(w / QUANT)), max(1, round(h / QUANT))
    key = (qw, qh, round(softness * 100))
    sprite = _CACHE.get(key)
    if sprite is None:
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
            _TINTED.clear()  # as versões tingidas apontam para os sprites descartados
        w, h = qw * QUANT, qh * QUANT
        blur = round(clamp(softness, 0.0, 2.0) * min(w, h) / 2)
        pad = 2 * blur
        size = (w + 2 * pad, h + 2 * pad)
        # Borda difusa não precisa de resolução cheia: borra numa versão reduzida e amplia (bem mais rápido).
        k = max(1, round(blur / BLUR_STEP))
        small = (max(1, round(size[0] / k)), max(1, round(size[1] / k)))
        sprite = pygame.Surface(small, pygame.SRCALPHA)
        pygame.draw.ellipse(sprite, (255, 255, 255, 255), (pad / k, pad / k, w / k, h / k))
        if blur >= 1:
            sprite = pygame.transform.gaussian_blur(sprite, max(1, round(blur / k)))
        if k > 1:
            sprite = pygame.transform.smoothscale(sprite, size)
        # O blur também escurece o RGB da borda; mantém branco puro e só o alfa varia.
        sprite.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
        _CACHE[key] = sprite
    return sprite


def blit_soft(
    surface: pygame.Surface,
    center: Tuple[float, float],
    w: float,
    h: float,
    color: RGB,
    alpha: float,
    softness: float = 0.35,
) -> None:
    """Desenha uma elipse suave de cor `color` e opacidade `alpha` (0..1) centrada em `center`."""
    a = round(255 * clamp(alpha))
    if a <= 0 or w < 1 or h < 1:
        return
    sprite = soft_ellipse(w, h, softness)
    key = (id(sprite), tuple(color), a)
    tinted = _TINTED.get(key)
    if tinted is None:
        tinted = sprite.copy()
        tinted.fill((*color, a), special_flags=pygame.BLEND_RGBA_MULT)
        _TINTED[key] = tinted
        if len(_TINTED) > TINTED_LIMIT:
            _TINTED.pop(next(iter(_TINTED)))
    surface.blit(tinted, tinted.get_rect(center=(round(center[0]), round(center[1]))))
