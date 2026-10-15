"""Keyframes escalares para animações roteirizadas (piscar, bocejo...)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from .easing import Easing, lerp, linear


@dataclass(frozen=True)
class Key:
    """Valor `value` no instante `t`; `ease` suaviza o trecho que termina nesta key."""

    t: float
    value: float
    ease: Easing = linear


class Track:
    def __init__(self, keys: Iterable[Key]):
        self.keys: List[Key] = sorted(keys, key=lambda k: k.t)
        if not self.keys:
            raise ValueError("Track precisa de ao menos uma key")

    @property
    def duration(self) -> float:
        return self.keys[-1].t

    def sample(self, t: float) -> float:
        keys = self.keys
        if t <= keys[0].t:
            return keys[0].value
        if t >= keys[-1].t:
            return keys[-1].value
        for prev, nxt in zip(keys, keys[1:]):
            if t <= nxt.t:
                span = nxt.t - prev.t
                u = 1.0 if span <= 0.0 else (t - prev.t) / span
                return lerp(prev.value, nxt.value, nxt.ease(u))
        return keys[-1].value

    def scaled(self, factor: float) -> "Track":
        """Mesma animação, `factor` vezes mais lenta (>1) ou mais rápida (<1)."""
        return Track(Key(k.t * factor, k.value, k.ease) for k in self.keys)

    def then(self, other: "Track", gap: float = 0.0) -> "Track":
        """Concatena `other` depois desta track, com um intervalo `gap`."""
        offset = self.duration + gap
        shifted = [Key(k.t + offset, k.value, k.ease) for k in other.keys]
        return Track([*self.keys, *shifted])
