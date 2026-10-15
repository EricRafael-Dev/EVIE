"""Bocejo: pálpebras descem, olhos se espremem e voltam devagar."""
from __future__ import annotations

from typing import Callable, Optional

from ..core.easing import ease_in_out_sine
from ..core.timeline import Key, Track
from ..model.params import EyeParams

YAWN = Track([
    Key(0.0, 0.0),
    Key(0.8, 1.0, ease_in_out_sine),
    Key(1.8, 1.0),
    Key(2.8, 0.0, ease_in_out_sine),
])


class YawnLayer:
    def __init__(self, on_finish: Optional[Callable[[], None]] = None):
        self.on_finish = on_finish
        self._t: Optional[float] = None

    @property
    def active(self) -> bool:
        return self._t is not None

    def trigger(self) -> None:
        if self._t is None:
            self._t = 0.0

    def update(self, dt: float) -> None:
        if self._t is None:
            return
        self._t += dt
        if self._t >= YAWN.duration:
            self._t = None
            if self.on_finish is not None:
                self.on_finish()

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        if self._t is None:
            return
        w = YAWN.sample(self._t)
        for eye in (left, right):
            eye.lid_top += 0.4 * w
            eye.h *= 1.0 - 0.15 * w
            eye.y += 0.06 * w
