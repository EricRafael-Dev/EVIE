"""Ruído de gradiente 1D com seed (sem dependências externas)."""
from __future__ import annotations

import random

from .easing import lerp


class Noise1D:
    """Ruído suave e determinístico; `noise(t)` devolve valores em [-1, 1]."""

    def __init__(self, seed: int = 0):
        rng = random.Random(seed)
        self._grad = [rng.uniform(-1.0, 1.0) for _ in range(256)]

    def __call__(self, t: float) -> float:
        i = int(t // 1)
        f = t - i
        g0 = self._grad[i & 255]
        g1 = self._grad[(i + 1) & 255]
        u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
        return lerp(g0 * f, g1 * (f - 1.0), u) * 2.0

    def fbm(self, t: float, octaves: int = 3) -> float:
        """Soma de oitavas, normalizada para [-1, 1]."""
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(octaves):
            total += amp * self(t * freq)
            norm += amp
            amp *= 0.5
            freq *= 2.0
        return total / norm
