"""Mola amortecida: basta mudar `target` e o valor se move de forma orgânica."""
from __future__ import annotations

import math


class Spring:
    """Oscilador harmônico amortecido.

    frequency: frequência natural em Hz (quanto maior, mais rápido).
    damping:   razão de amortecimento (1 = crítico, < 1 = com overshoot).
    """

    MAX_STEP = 1.0 / 240.0  # sub-passos mantêm a integração estável com dt grande

    def __init__(self, value: float = 0.0, frequency: float = 4.0, damping: float = 0.8):
        self.value = float(value)
        self.target = float(value)
        self.velocity = 0.0
        self.frequency = frequency
        self.damping = damping

    def update(self, dt: float) -> float:
        if dt <= 0.0:
            return self.value
        steps = max(1, math.ceil(dt / self.MAX_STEP))
        h = dt / steps
        omega = 2.0 * math.pi * self.frequency
        k = omega * omega
        c = 2.0 * self.damping * omega
        for _ in range(steps):
            self.velocity += (k * (self.target - self.value) - c * self.velocity) * h
            self.value += self.velocity * h
        return self.value

    def snap(self, value: float | None = None) -> None:
        """Teleporta para `value` (ou para o alvo atual) sem movimento."""
        if value is not None:
            self.target = float(value)
        self.value = self.target
        self.velocity = 0.0

    def settled(self, eps: float = 1e-3) -> bool:
        return abs(self.target - self.value) < eps and abs(self.velocity) < eps
