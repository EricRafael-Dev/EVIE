"""Cache LRU simples para formas que só dependem do tamanho (máscaras do `^`, símbolos, rampas)."""
from __future__ import annotations

from collections import OrderedDict
from typing import Callable, Hashable, Tuple

import pygame


class LruCache:
    def __init__(self, limit: int):
        self.limit = limit
        self._items: "OrderedDict[Hashable, pygame.Surface]" = OrderedDict()

    def get(self, key: Hashable, build: Callable[[], pygame.Surface]) -> pygame.Surface:
        item = self._items.get(key)
        if item is None:
            item = build()
            self._items[key] = item
            if len(self._items) > self.limit:
                self._items.popitem(last=False)
        else:
            self._items.move_to_end(key)
        return item

    def clear(self) -> None:
        self._items.clear()


def blit_tinted(surface: pygame.Surface, mask: pygame.Surface, topleft: Tuple[int, int], color: Tuple[int, int, int]) -> None:
    """Desenha `mask` (branca com alfa) na cor `color`: o resultado é o mesmo de ter desenhado direto nessa cor."""
    tinted = mask.copy()
    tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(tinted, topleft)
