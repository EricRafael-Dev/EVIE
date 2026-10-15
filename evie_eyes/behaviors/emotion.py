"""Camadas ligadas às emoções: tremor de raiva, pulinho de alegria e pulso dos olhos-símbolo."""
from __future__ import annotations

import math
import random

from ..core.noise import Noise1D
from ..core.spring import Spring
from ..effects.particles import heartbeat
from ..model.params import EyeParams

TREMBLE_AMP = 0.035   # deslocamento máximo do tremor (unidades de olhar)
TREMBLE_SPEED = 18.0  # rapidez do ruído do tremor
BEAT_GLOW = 0.6       # quanto o brilho cresce no pico do batimento
HOP_VELOCITY = 9.0    # impulso inicial do pulinho (unidades de olhar/s)
HEART_PULSE = 0.13    # quanto o coração incha no "tum" do batimento
HEART_PERIOD = 1.0    # segundos por batimento duplo
STAR_PULSE = 0.07     # amplitude do brilhar da estrela
STAR_PERIOD = 1.3


class GlyphPulseLayer:
    """Olhos de coração batem como um coração; olhos de estrela cintilam."""

    def __init__(self) -> None:
        self.enabled = True
        self._time = 0.0

    def update(self, dt: float) -> None:
        self._time += dt

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        if not self.enabled:
            return
        beat = heartbeat(self._time, HEART_PERIOD)
        twinkle = math.sin(2.0 * math.pi * self._time / STAR_PERIOD)
        for eye in (left, right):
            if eye.glyph == "heart":
                scale = 1.0 + HEART_PULSE * beat
                eye.glow *= 1.0 + 0.25 * beat
            elif eye.glyph == "star":
                scale = 1.0 + STAR_PULSE * twinkle
                eye.glow *= 1.0 + 0.2 * (0.5 + 0.5 * twinkle)
            else:
                continue
            eye.w *= scale
            eye.h *= scale


class TrembleLayer:
    """Lê `tremble` de cada olho: treme e faz o brilho pulsar como um coração acelerado."""

    def __init__(self, rng: random.Random):
        self.enabled = True
        self._nx = Noise1D(rng.randrange(1 << 30))
        self._ny = Noise1D(rng.randrange(1 << 30))
        self._time = 0.0

    def update(self, dt: float) -> None:
        self._time += dt

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        if not self.enabled:
            return
        t = self._time
        beat = heartbeat(t)
        for eye in (left, right):
            k = eye.tremble
            if k <= 0.01:
                continue
            eye.x += k * TREMBLE_AMP * self._nx(t * TREMBLE_SPEED)
            eye.y += k * TREMBLE_AMP * self._ny(t * TREMBLE_SPEED)
            eye.glow *= 1.0 + k * BEAT_GLOW * beat


class HopLayer:
    """Pulinho elástico: `kick()` lança os olhos para cima e uma mola traz de volta quicando."""

    def __init__(self) -> None:
        self.enabled = True
        self._spring = Spring(0.0, frequency=3.2, damping=0.35)

    @property
    def offset(self) -> float:
        return self._spring.value

    def kick(self, strength: float = 1.0) -> None:
        if self.enabled:
            self._spring.velocity -= HOP_VELOCITY * strength

    def update(self, dt: float) -> None:
        self._spring.update(dt)

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        for eye in (left, right):
            eye.y += self._spring.value
