"""Efeitos por emoção: dispara as partículas e comportamentos listados em `fx:` de cada preset."""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Callable, Dict, List, Sequence, Tuple

from ..model.geometry import EYE_H, EYE_W, eye_center
from ..model.params import EyeParams
from .particles import Color, Particle, ParticleSystem

if TYPE_CHECKING:
    from ..face import Face

# Efeitos contínuos e o intervalo (s) entre emissões.
CONTINUOUS: Dict[str, Tuple[float, float]] = {
    "tears": (1.6, 3.0),
    "zzz": (1.1, 1.6),
    "sparkles": (0.5, 1.2),
    "hearts": (0.45, 0.9),
}
ONE_SHOT = frozenset({"hop", "wink_sparkle", "shockwave", "exclaim"})
PERSISTENT = frozenset({"anger"})  # fica na tela enquanto a expressão durar
MODES = frozenset({"scan"})        # mudam um comportamento em vez de criar partículas
FX_KINDS = frozenset(CONTINUOUS) | ONE_SHOT | PERSISTENT | MODES

TEAR_COLOR: Color = (150.0, 205.0, 255.0)
HEART_COLOR: Color = (255.0, 110.0, 160.0)
SPARKLE_COLOR: Color = (255.0, 248.0, 215.0)
ANGER_COLOR: Color = (255.0, 80.0, 70.0)
EXCLAIM_COLOR: Color = (255.0, 225.0, 110.0)
HOP_DELAY = 0.22  # espera o olho reabrir (troca de forma no piscar) antes do pulinho


def validate_fx(name: str, fx: Sequence[str]) -> None:
    unknown = sorted(set(fx) - FX_KINDS)
    if unknown:
        raise ValueError(f"Preset {name!r}: efeitos desconhecidos {unknown}. Disponíveis: {sorted(FX_KINDS)}")


class EmotionFX:
    def __init__(self, face: "Face", rng: random.Random):
        self.face = face
        self.rng = rng
        self.particles = ParticleSystem()
        self.active: Tuple[str, ...] = ()
        self._timers: Dict[str, float] = {}
        self._scheduled: List[List] = []  # [segundos restantes, callback]
        self._persistent: Dict[str, Particle] = {}

    # --- API ---------------------------------------------------------------

    def on_expression(self, fx: Sequence[str]) -> None:
        wanted = set(fx)
        for kind in list(self._persistent):
            if kind not in wanted:
                self._persistent.pop(kind).release()
        self._scheduled.clear()
        self._timers = {kind: self.rng.uniform(0.15, 0.5) for kind in fx if kind in CONTINUOUS}
        self.face.saccade.scan = "scan" in wanted

        for kind in fx:
            if kind == "hop":
                self._schedule(HOP_DELAY, self.face.hop.kick)
            elif kind == "wink_sparkle":
                self._schedule(0.25, lambda: self._wink_sparkle(0.62, -0.42, 0.2))
                self._schedule(0.45, lambda: self._wink_sparkle(0.8, -0.2, 0.12))
            elif kind == "shockwave":
                for side in (-1, 1):
                    self._shockwave(side)
            elif kind == "exclaim":
                self._exclaim()
            elif kind == "anger" and kind not in self._persistent:
                self._persistent[kind] = self.particles.spawn(Particle(
                    "anger", *self._anger_anchor(), size=0.3, life=math.inf,
                    color=ANGER_COLOR, fade_in=0.25, fade_out=0.3,
                ))
        self.active = tuple(fx)

    def update(self, dt: float) -> None:
        for item in self._scheduled:
            item[0] -= dt
        due = [callback for remaining, callback in self._scheduled if remaining <= 0.0]
        self._scheduled = [item for item in self._scheduled if item[0] > 0.0]
        for callback in due:
            callback()

        for kind, remaining in list(self._timers.items()):
            remaining -= dt
            if remaining <= 0.0:
                self._emit(kind)
                remaining = self.rng.uniform(*CONTINUOUS[kind])
            self._timers[kind] = remaining

        anger = self._persistent.get("anger")
        if anger is not None:
            anger.x, anger.y = self._anger_anchor()
        self.particles.update(dt)

    # --- emissores -----------------------------------------------------------

    def _schedule(self, delay: float, callback: Callable[[], None]) -> None:
        self._scheduled.append([delay, callback])

    def _eye(self, side: int) -> EyeParams:
        return self.face.eyes[0 if side < 0 else 1]

    def _emit(self, kind: str) -> None:
        if kind == "tears":
            self._tear()
        elif kind == "zzz":
            self._zzz()
        elif kind == "sparkles":
            self._sparkle()
        elif kind == "hearts":
            self._heart()

    def _tear(self) -> None:
        side = self.rng.choice((-1, 1))
        p = self._eye(side)
        cx, cy = eye_center(p, side)
        self.particles.spawn(Particle(
            "tear",
            cx + side * 0.36 * EYE_W * p.w,  # canto externo, onde a lágrima se acumula
            cy + 0.42 * EYE_H * p.h,
            size=0.09, life=1.9, color=TEAR_COLOR,
            vx=side * 0.01, vy=0.02, ay=1.6, hold=0.7, fade_in=0.05, fade_out=0.3,
        ))

    def _zzz(self) -> None:
        p = self._eye(1)
        cx, cy = eye_center(p, 1)
        light = tuple(c + (255.0 - c) * 0.3 for c in p.color)
        self.particles.spawn(Particle(
            "zzz", cx + 0.45 * EYE_W, cy - 0.12 * EYE_H,
            size=0.16, life=2.6, color=light,  # type: ignore[arg-type]
            vx=0.035, vy=-0.075, angle=-0.2, phase=self.rng.uniform(0.0, 2.0 * math.pi),
            fade_in=0.4, fade_out=0.9,
        ))

    def _heart(self) -> None:
        side = self.rng.choice((-1, 1))
        cx, cy = eye_center(self._eye(side), side)
        self.particles.spawn(Particle(
            "heart", cx + self.rng.uniform(-0.4, 0.4) * EYE_W, cy - 0.5 * EYE_H,
            size=self.rng.uniform(0.12, 0.2), life=self.rng.uniform(1.8, 2.4), color=HEART_COLOR,
            vx=self.rng.uniform(-0.01, 0.01), vy=-self.rng.uniform(0.07, 0.11),
            phase=self.rng.uniform(0.0, 2.0 * math.pi), fade_in=0.25, fade_out=0.8,
        ))

    def _sparkle(self) -> None:
        side = self.rng.choice((-1, 1))
        cx, cy = eye_center(self._eye(side), side)
        a = self.rng.uniform(math.radians(200), math.radians(340))  # metade de cima, fora do olho
        self.particles.spawn(Particle(
            "sparkle", cx + math.cos(a) * 0.75 * EYE_W, cy + math.sin(a) * 0.55 * EYE_H,
            size=self.rng.uniform(0.09, 0.15), life=self.rng.uniform(0.6, 0.9), color=SPARKLE_COLOR,
            spin=self.rng.uniform(-1.5, 1.5), fade_in=0.0, fade_out=0.0,
        ))

    def _wink_sparkle(self, fx: float, fy: float, size: float) -> None:
        cx, cy = eye_center(self._eye(1), 1)
        self.particles.spawn(Particle(
            "sparkle", cx + fx * EYE_W, cy + fy * EYE_H, size=size, life=0.9,
            color=SPARKLE_COLOR, spin=1.2, fade_in=0.0, fade_out=0.0,
        ))

    def _shockwave(self, side: int) -> None:
        p = self._eye(side)
        cx, cy = eye_center(p, side)
        self.particles.spawn(Particle(
            "ring", cx, cy, size=0.55 * max(p.h, 1.0), size_x=0.55 * max(p.w, 1.0), life=0.6,
            color=p.color, layer="back", fade_in=0.0, fade_out=0.6,
        ))

    def _exclaim(self) -> None:
        cx, cy = eye_center(self._eye(1), 1)
        self.particles.spawn(Particle(
            "exclaim", cx + 0.64 * EYE_W, cy - 0.62 * EYE_H, size=0.42, life=1.1,
            color=EXCLAIM_COLOR, angle=0.18, fade_in=0.0, fade_out=0.3,
        ))

    def _anger_anchor(self) -> Tuple[float, float]:
        cx, cy = eye_center(self._eye(1), 1)
        return cx + 0.6 * EYE_W, cy - 0.55 * EYE_H
