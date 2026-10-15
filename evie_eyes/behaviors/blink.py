"""Piscar: intervalos aleatórios, piscada dupla e leve defasagem entre os olhos."""
from __future__ import annotations

import random
from typing import Optional, Tuple

from ..core.easing import ease_in_quad, ease_out_cubic
from ..core.timeline import Key, Track
from ..model.params import EyeParams

SINGLE_BLINK = Track([
    Key(0.00, 0.0),
    Key(0.07, 1.0, ease_in_quad),
    Key(0.11, 1.0),
    Key(0.26, 0.0, ease_out_cubic),
])
DOUBLE_BLINK = SINGLE_BLINK.then(SINGLE_BLINK, gap=0.08)
CLOSED_RESIDUE = 0.04  # fração de altura que sobra com o olho "fechado" (linha fina)
BLINK_SQUASH = 0.12    # o olho alarga um pouco ao fechar (squash & stretch)


class BlinkLayer:
    def __init__(
        self,
        rng: random.Random,
        interval: Tuple[float, float] = (2.0, 6.0),
        double_chance: float = 0.15,
        max_eye_delay: float = 0.02,
    ):
        self.rng = rng
        self.interval = interval
        self.double_chance = double_chance
        self.max_eye_delay = max_eye_delay
        self.enabled = True
        self.rate = 1.0  # >1 pisca mais, <1 pisca menos
        self._track: Track = SINGLE_BLINK
        self._t: Optional[float] = None
        self._delay = 0.0
        self._next = rng.uniform(*interval)

    @property
    def blinking(self) -> bool:
        return self._t is not None

    @property
    def closure(self) -> float:
        """Quanto os dois olhos estão fechados (vale o menos fechado), 0..1."""
        if self._t is None:
            return 0.0
        return min(self._track.sample(self._t), self._track.sample(self._t - self._delay))

    def cancel(self) -> None:
        self._t = None

    def trigger(self, double: bool = False, slow: bool = False) -> None:
        track = DOUBLE_BLINK if double else SINGLE_BLINK
        self._track = track.scaled(2.0) if slow else track
        self._delay = self.rng.uniform(0.0, self.max_eye_delay)
        self._t = 0.0

    def update(self, dt: float) -> None:
        if self._t is not None:
            self._t += dt
            if self._t > self._track.duration + self._delay:
                self._t = None
        if self._t is None and self.enabled:
            self._next -= dt * max(self.rate, 0.0)
            if self._next <= 0.0:
                self.trigger(double=self.rng.random() < self.double_chance)
                self._next = self.rng.uniform(*self.interval)

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        if self._t is None:
            return
        for eye, delay in ((left, 0.0), (right, self._delay)):
            closure = self._track.sample(self._t - delay)
            eye.h *= 1.0 - (1.0 - CLOSED_RESIDUE) * closure
            eye.w *= 1.0 + BLINK_SQUASH * closure
