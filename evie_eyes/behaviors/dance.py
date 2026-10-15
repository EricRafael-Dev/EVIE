"""Animação de dança: olhos felizes (^ ^), saltitando e balançando de um lado para o outro."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from ..model.params import EyeParams

if TYPE_CHECKING:
    from ..face import Face


class DanceLayer:
    """Camada de dança rítmica com olhos felizes (^ ^), trajetória em arco a 120 BPM e balanço lateral."""

    def __init__(self, face: "Face", bpm: float = 120.0):
        self.face = face
        self.bpm = bpm
        self.enabled = False
        self._time = 0.0
        self._duration = 0.0
        self._prev_expression: Optional[str] = None

    @property
    def dancing(self) -> bool:
        return self.enabled and self._duration > 0.0

    def trigger(self, duration: float = 4.5) -> None:
        """Inicia a dança com olhos felizes (^ ^), balanço em arco a 120 BPM."""
        self.enabled = True
        self._time = 0.0
        self._duration = duration
        self._prev_expression = self.face.expression
        self.face.set_expression("happy")
        # Dispara partículas festivas se existirem
        if hasattr(self.face, "fx") and hasattr(self.face.fx, "burst"):
            try:
                self.face.fx.burst("star", 10)
            except Exception:
                pass

    def stop(self) -> None:
        """Para a dança e restaura o estado anterior com uma piscadinha suave de transição."""
        if self.enabled:
            self.enabled = False
            self._duration = 0.0
            if self.face.expression == "happy":
                prev = self._prev_expression or "neutral"
                self.face.set_expression(prev, source="idle")
            # Pisca na transição para o estado normal
            if hasattr(self.face, "blink_now"):
                self.face.blink_now()
            elif hasattr(self.face, "blink") and hasattr(self.face.blink, "trigger"):
                self.face.blink.trigger()

    def update(self, dt: float) -> None:
        if not self.enabled:
            return
        self._time += dt
        self._duration -= dt
        if self._duration <= 0.0:
            self.stop()

    def apply(self, left: EyeParams, right: EyeParams) -> None:
        if not self.enabled:
            return
        # A 120 BPM temos 2 batidas por segundo (1 batida = 0.5s para cada arco lateral)
        cycle_freq = (self.bpm / 120.0) * 1.0  # 1.0 Hz a 120 BPM
        cycle_phase = self._time * cycle_freq * 2.0 * math.pi

        # 1. Balanço lateral do centro do rosto (de um lado para o outro)
        norm_x = math.sin(cycle_phase)
        sway = norm_x * 0.36

        # 2. Curva base do arco parabólico
        arc_curve = 1.0 - norm_x * norm_x  # 1.0 no topo central, 0.0 nas pontas
        center_y = -arc_curve * 0.16 + 0.04

        # 3. Trajetória de ARCO ÚNICO para o par de olhos:
        # Quando vai para a direita (norm_x > 0):
        # - O olho direito desce pela curvatura do arco (+diff_y)
        # - O olho esquerdo sobe (-diff_y)
        # - Ambos inclinam para o lado que está indo (tilt)
        diff_y = norm_x * 0.13
        tilt = -norm_x * 0.22

        # 4. Deformação squash & stretch sutil no ritmo do arco
        squash = (arc_curve - 0.45) * 0.07

        # Olho esquerdo
        left.x += sway
        left.y += center_y - diff_y   # sobe quando vai para a direita
        left.lid_tilt += tilt
        left.lid_top = 0.0
        left.lid_bottom = 0.0
        left.w *= 1.0 - squash * 0.6
        left.h *= 1.0 + squash
        left.arc = max(left.arc, 0.95)
        left.glow *= 1.25
        left.blush = min(1.0, left.blush + 0.40)

        # Olho direito
        right.x += sway
        right.y += center_y + diff_y  # desce quando vai para a direita
        right.lid_tilt += tilt
        right.lid_top = 0.0
        right.lid_bottom = 0.0
        right.w *= 1.0 - squash * 0.6
        right.h *= 1.0 + squash
        right.arc = max(right.arc, 0.95)
        right.glow *= 1.25
        right.blush = min(1.0, right.blush + 0.40)
