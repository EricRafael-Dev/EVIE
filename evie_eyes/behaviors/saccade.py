"""Sacadas: olhadas rápidas para pontos aleatórios, com pequena assimetria entre os olhos."""
from __future__ import annotations

import math
import random
from typing import Callable, Optional, Tuple

from ..core.easing import clamp
from ..core.spring import Spring
from ..model.params import EyeParams

STRETCH_PER_SPEED = 0.008  # deformação por unidade de velocidade do olhar (1/s)
STRETCH_MAX = 0.12
SCAN_SPEED = 0.32          # no modo varredura as molas do olhar ficam ~3x mais lentas
SCAN_HOLD = (1.2, 2.0)     # segundos olhando para cada lado na varredura


class SaccadeLayer:
    def __init__(
        self,
        rng: random.Random,
        hold: Tuple[float, float] = (0.5, 3.0),
        range_x: float = 0.8,
        range_y: float = 0.5,
        center_bias: float = 0.35,
        on_shift: Optional[Callable[[float], None]] = None,
    ):
        self.rng = rng
        self.hold = hold
        self.range_x = range_x
        self.range_y = range_y
        self.center_bias = center_bias
        self.on_shift = on_shift
        self.enabled = True
        self.activity = 1.0  # >1 muda o olhar com mais frequência
        self._timer = rng.uniform(*hold)
        self._tx = 0.0
        self._ty = 0.0
        # Molas elásticas com bounce suave e orgânico (underdamped harmonic oscillator)
        # O olho direito possui leve defasagem temporal criando atraso visual tridimensional
        self._left = (Spring(frequency=5.8, damping=0.52), Spring(frequency=5.8, damping=0.52))
        self._right = (Spring(frequency=5.2, damping=0.56), Spring(frequency=5.2, damping=0.56))
        self._scan = False
        self._tracking = False
        self._travel_accum = 0.0
        self._micro_timer = rng.uniform(2.5, 4.5)

    @property
    def scan(self) -> bool:
        """Modo desconfiado: o olhar varre devagar de um lado para o outro."""
        return self._scan

    @scan.setter
    def scan(self, value: bool) -> None:
        if value == self._scan:
            return
        self._scan = value
        slow = SCAN_SPEED if value else 1.0
        for (sx, sy), freq in ((self._left, 7.0), (self._right, 6.4)):
            sx.frequency = sy.frequency = freq * slow
        if value:
            self._timer = min(self._timer, 0.3)

    def track(self, x: float, y: float) -> None:
        """Rastreamento contínuo de olhar (ex.: cursor do mouse).
        Mantém os alvos das molas nas coordenadas fornecidas sem interrupção de sacadas aleatórias."""
        self._tracking = True
        self._set_target(clamp(x, -1.0, 1.0), clamp(y, -1.0, 1.0))
        self._timer = 1.0

    def stop_tracking(self) -> None:
        """Encerra o rastreamento contínuo e retorna suavemente ao ciclo de sacadas naturais."""
        if self._tracking:
            self._tracking = False
            self._timer = 0.8

    def look_at(self, x: float, y: float, hold: float = 2.0) -> None:
        self._tracking = False
        self._set_target(clamp(x, -1.0, 1.0), clamp(y, -1.0, 1.0))
        self._timer = hold

    def _set_target(self, x: float, y: float) -> None:
        dist = math.hypot(x - self._tx, y - self._ty)
        self._tx, self._ty = x, y
        if self._tracking:
            self._travel_accum += dist
            # Movimentos amplos do mouse pela tela disparam piscadas orgânicas
            if self._travel_accum > 0.85:
                self._travel_accum = 0.0
                if self.on_shift is not None:
                    self.on_shift(0.6)
        elif dist > 0.02 and self.on_shift is not None:
            self.on_shift(dist)

    def _pick(self) -> None:
        rng = self.rng
        if self._scan:
            side = -1.0 if self._tx > 0.0 else 1.0 if self._tx < 0.0 else rng.choice((-1.0, 1.0))
            self._set_target(side * rng.uniform(0.45, 0.7), rng.uniform(-0.05, 0.1))
            self._timer = rng.uniform(*SCAN_HOLD)
            return
        if rng.random() < self.center_bias:
            x, y = rng.gauss(0.0, 0.08), rng.gauss(0.0, 0.06)
        else:
            x = clamp(rng.gauss(0.0, 0.5), -self.range_x, self.range_x)
            y = clamp(rng.gauss(0.0, 0.3), -self.range_y, self.range_y)
        self._set_target(x, y)
        self._timer = rng.uniform(*self.hold) / max(self.activity, 0.1)

    def update(self, dt: float) -> None:
        if self.enabled:
            if not self._tracking:
                self._timer -= dt
                if self._timer <= 0.0:
                    self._pick()
            else:
                # Durante o rastreamento contínuo, mantém micro-sacadas vivas de fixação
                self._micro_timer -= dt
                if self._micro_timer <= 0.0:
                    self._micro_timer = self.rng.uniform(2.2, 4.5)
                    self._tx = clamp(self._tx + self.rng.gauss(0.0, 0.02), -1.0, 1.0)
                    self._ty = clamp(self._ty + self.rng.gauss(0.0, 0.015), -1.0, 1.0)
            tx, ty = self._tx, self._ty
        else:
            tx = ty = 0.0
        for sx, sy in (self._left, self._right):
            sx.target, sy.target = tx, ty
            sx.update(dt)
            sy.update(dt)

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        for eye, (sx, sy) in ((left, self._left), (right, self._right)):
            eye.x += sx.value
            eye.y += sy.value
            # Stretch na direção do movimento, preservando o "volume" no outro eixo.
            stretch_x = min(abs(sx.velocity) * STRETCH_PER_SPEED, STRETCH_MAX)
            stretch_y = min(abs(sy.velocity) * STRETCH_PER_SPEED, STRETCH_MAX)
            eye.w *= 1.0 + stretch_x - 0.5 * stretch_y
            eye.h *= 1.0 + stretch_y - 0.5 * stretch_x

        # Perspectiva 3D orgânica (Head Turn Parallax):
        # Quando o mouse vai para a direita, o olho esquerdo aumenta suavemente de acordo
        # com a distância do cursor; e vice-versa quando o mouse vai para a esquerda.
        gaze_x = (self._left[0].value + self._right[0].value) * 0.5
        if gaze_x > 0.0:
            left_scale = 1.0 + min(0.35, gaze_x * 0.24)
            right_scale = 1.0 - min(0.08, gaze_x * 0.05)
        else:
            right_scale = 1.0 + min(0.35, abs(gaze_x) * 0.24)
            left_scale = 1.0 - min(0.08, abs(gaze_x) * 0.05)

        left.w *= left_scale
        left.h *= left_scale
        right.w *= right_scale
        right.h *= right_scale
