"""Respiração (escala + leve vaivém vertical) e micro-movimento do olhar por ruído."""
from __future__ import annotations

import math
import random

from ..core.noise import Noise1D
from ..model.params import EyeParams

DEFAULT_PERIOD = 4.0
DEFAULT_AMPLITUDE = 0.02
DEFAULT_BOB = 0.01
GLOW_PULSE = 8.0  # o brilho pulsa GLOW_PULSE vezes mais que a escala (respiração "acesa")


class BreathingLayer:
    def __init__(self, rng: random.Random):
        self.enabled = True
        self.period = DEFAULT_PERIOD
        self.amplitude = DEFAULT_AMPLITUDE  # escala do olho (+-)
        self.bob = DEFAULT_BOB              # deslocamento vertical (+-)
        self._amp = self.amplitude
        self._bob = self.bob
        self._phase = rng.uniform(0.0, 2.0 * math.pi)
        self._noise = Noise1D(rng.randrange(1 << 30))
        self._time = 0.0

    def reset_defaults(self) -> None:
        self.period, self.amplitude, self.bob = DEFAULT_PERIOD, DEFAULT_AMPLITUDE, DEFAULT_BOB

    def update(self, dt: float) -> None:
        self._time += dt
        # Período varia lentamente: a respiração nunca fica perfeitamente periódica.
        period = self.period * (1.0 + 0.12 * self._noise(self._time * 0.15))
        self._phase += dt / max(period, 0.1) * 2.0 * math.pi
        k = 1.0 - math.exp(-2.0 * dt)  # suaviza trocas de amplitude
        self._amp += (self.amplitude - self._amp) * k
        self._bob += (self.bob - self._bob) * k

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        if not self.enabled:
            return
        s = math.sin(self._phase)
        for eye in (left, right):
            if eye.h < 0.2:
                # Olhos fechados ou semi-fechados (dormindo/piscando): respiração viva com pulso na espessura e heave vertical
                eye.h = max(0.035, eye.h + self._amp * 0.35 * s)
                eye.w *= 1.0 + self._amp * 0.4 * s
                eye.y += self._bob * s
                eye.glow *= 1.0 + min(1.2, GLOW_PULSE * self._amp) * s
            else:
                eye.h *= 1.0 + self._amp * s
                eye.w *= 1.0 + self._amp * 0.5 * s
                eye.y += self._bob * s
                eye.glow *= 1.0 + GLOW_PULSE * self._amp * s


class DriftLayer:
    """Micro-movimento contínuo do olhar: evita olhos "mortos"."""

    def __init__(self, rng: random.Random, amplitude: float = 0.025, speed: float = 0.7):
        self.enabled = True
        self.amplitude = amplitude
        self.speed = speed
        self._nx = Noise1D(rng.randrange(1 << 30))
        self._ny = Noise1D(rng.randrange(1 << 30))
        self._time = rng.uniform(0.0, 100.0)

    def update(self, dt: float) -> None:
        self._time += dt

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        if not self.enabled:
            return
        t = self._time * self.speed
        dx = self.amplitude * self._nx.fbm(t)
        dy = self.amplitude * self._ny.fbm(t)
        for eye in (left, right):
            eye.x += dx
            eye.y += dy
