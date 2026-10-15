"""Estado IDLE: vida própria, tédio crescente, bocejo e sono."""
from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..face import Face

ACTIVE, BORED, SLEEPY, ASLEEP = "active", "bored", "sleepy", "asleep"


@dataclass
class IdleConfig:
    """Tempos (s) desde o último estímulo."""

    enabled: bool = True
    bored_after: float = 20.0   # passa a olhar em volta com mais frequência
    yawn_after: float = 40.0    # boceja uma vez
    sleepy_after: float = 60.0  # pálpebras caídas, pisca devagar
    sleep_after: float = 80.0   # dorme
    jitter: float = 0.15        # variação aleatória (+-) nos tempos acima

    @classmethod
    def fast(cls, factor: float = 0.2) -> "IdleConfig":
        """Versão acelerada, boa para demonstração e testes."""
        base = cls()
        return replace(
            base,
            bored_after=base.bored_after * factor,
            yawn_after=base.yawn_after * factor,
            sleepy_after=base.sleepy_after * factor,
            sleep_after=base.sleep_after * factor,
        )


class IdleController:
    def __init__(self, face: "Face", config: IdleConfig, rng: random.Random):
        self.face = face
        self.config = config
        self.rng = rng
        self.stage = ACTIVE
        self.clock = 0.0
        self._yawned = False
        self._roll_thresholds()

    def _roll_thresholds(self) -> None:
        cfg = self.config
        values = sorted(
            base * self.rng.uniform(1.0 - cfg.jitter, 1.0 + cfg.jitter)
            for base in (cfg.bored_after, cfg.yawn_after, cfg.sleepy_after, cfg.sleep_after)
        )
        self._bored, self._yawn, self._sleepy, self._sleep = values

    def reset(self) -> None:
        """Um estímulo chegou: volta ao comportamento normal."""
        if self.stage in (SLEEPY, ASLEEP):
            self.face.set_expression("neutral", source="idle")
        self._restore_layers()
        self.stage = ACTIVE
        self.clock = 0.0
        self._yawned = False
        self._roll_thresholds()

    def wake(self) -> None:
        """Acorda o robô; se estava dormindo, ele se assusta antes de relaxar."""
        was_asleep = self.stage == ASLEEP
        self.reset()
        if was_asleep:
            self.face.set_expression("surprised", duration=0.9, source="idle")
            self.face.blink.trigger(double=True)

    def sleep_now(self) -> None:
        self._enter(ASLEEP)

    def update(self, dt: float) -> None:
        if not self.config.enabled:
            return
        # O relógio só corre quando a expressão é "neutral" ou foi o próprio IDLE que a definiu.
        if self.stage in (ACTIVE, BORED) and self.face.expression != "neutral":
            return
        self.clock += dt
        if self.stage == ACTIVE and self.clock >= self._bored:
            self._enter(BORED)
        if self.stage == BORED and not self._yawned and self.clock >= self._yawn:
            self._yawned = True
            self.face.yawn.trigger()
        if self.stage in (ACTIVE, BORED) and self.clock >= self._sleepy:
            self._enter(SLEEPY)
        if self.stage == SLEEPY and self.clock >= self._sleep:
            self._enter(ASLEEP)

    def _restore_layers(self) -> None:
        face = self.face
        face.saccade.enabled = True
        face.saccade.activity = 1.0
        face.blink.enabled = True
        face.blink.rate = 1.0
        face.breathing.reset_defaults()

    def _enter(self, stage: str) -> None:
        face = self.face
        self._restore_layers()
        self.stage = stage
        if stage == BORED:
            face.saccade.activity = 1.8
        elif stage == SLEEPY:
            face.set_expression("sleepy", source="idle")
            face.saccade.activity = 0.35
            face.blink.rate = 0.5
            face.breathing.period = 5.5
        elif stage == ASLEEP:
            face.set_expression("asleep", source="idle")
            face.saccade.enabled = False
            face.blink.enabled = False
            face.breathing.period = 6.5
            face.breathing.amplitude = 0.04
            face.breathing.bob = 0.05
