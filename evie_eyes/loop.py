"""Controle do loop da janela: limitador de FPS preciso, qualidade adaptativa e cache de texto do HUD."""
from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Sequence

import pygame

SLEEP_MARGIN = 0.0025  # s: o que sobra dessa margem antes do prazo é espera ocupada (o sleep do SO erra ~1 ms)


class FramePacer:
    """Limita o loop a `fps` quadros por segundo com precisão de microssegundos.

    `clock.tick(144)` do pygame trunca o período para milissegundos inteiros (6 ms ≈ 166 fps), então não
    serve para taxas altas. Aqui dorme-se a maior parte da espera e o restante é espera ocupada.
    `fps <= 0` não limita. `wait()` devolve o tempo (s) desde o frame anterior.
    """

    def __init__(
        self,
        fps: float,
        clock: Callable[[], float] = time.perf_counter,
        sleep_ms: Callable[[int], object] = pygame.time.wait,
    ):
        self.period = 1.0 / fps if fps > 0 else 0.0
        self._clock = clock
        self._sleep_ms = sleep_ms
        now = clock()
        self._deadline = now + self.period
        self._previous = now

    def wait(self) -> float:
        if self.period > 0.0:
            remaining = self._deadline - self._clock()
            if remaining > SLEEP_MARGIN:
                self._sleep_ms(int((remaining - SLEEP_MARGIN) * 1000))
            while self._clock() < self._deadline:
                pass
        now = self._clock()
        if self.period > 0.0:
            # Se perdeu o prazo por mais de um período (pausa, arrastar a janela), recomeça em vez de "correr atrás".
            self._deadline = self._deadline + self.period if now - self._deadline < self.period else now + self.period
        dt = now - self._previous
        self._previous = now
        return dt


class AutoQuality:
    """Baixa o nível de qualidade quando o custo médio por frame não cabe no orçamento do FPS alvo.

    Alimente com o custo (ms) de cada frame (sem contar a espera do limitador). Quando a média móvel passa
    de `slack` x orçamento por `patience` frames seguidos, `update` devolve o próximo nível mais leve.
    Nunca sobe sozinho (o `Q` do app continua trocando manualmente).
    """

    def __init__(self, fps: float, levels: Sequence[str], slack: float = 0.92, patience: int = 60):
        self.budget_ms = 1000.0 / fps if fps > 0 else float("inf")
        self.levels = list(levels)
        self.slack = slack
        self.patience = patience
        self._average: Optional[float] = None
        self._slow = 0

    @property
    def average_ms(self) -> float:
        return self._average or 0.0

    def update(self, cost_ms: float, current: str) -> Optional[str]:
        self._average = cost_ms if self._average is None else self._average * 0.9 + cost_ms * 0.1
        self._slow = self._slow + 1 if self._average > self.budget_ms * self.slack else 0
        index = self.levels.index(current)
        if self._slow >= self.patience and index > 0:
            self._slow = 0
            self._average = None  # o novo nível ganha uma média nova
            return self.levels[index - 1]
        return None


class HudText:
    """Texto do HUD com cache: `font.render` custa mais que o desenho dos próprios olhos em 144 fps."""

    def __init__(self, font: pygame.font.Font, color=(120, 130, 130), limit: int = 24):
        self.font = font
        self.color = color
        self.limit = limit
        self._cache: Dict[str, pygame.Surface] = {}

    def get(self, text: str) -> pygame.Surface:
        surface = self._cache.get(text)
        if surface is None:
            if len(self._cache) >= self.limit:
                self._cache.pop(next(iter(self._cache)))
            surface = self._cache[text] = self.font.render(text, True, self.color)
        return surface
