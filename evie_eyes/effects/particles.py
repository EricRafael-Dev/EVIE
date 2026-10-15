"""Partículas simples (lágrimas, Zzz, brilhos...) em coordenadas normalizadas da tela."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..core.easing import clamp

Color = Tuple[float, float, float]
MAX_PARTICLES = 64


@dataclass
class Particle:
    """Uma partícula. Posição/velocidade em frações da tela; tamanhos em alturas de olho base.

    `hold`: segundos parada no lugar enquanto "nasce" (ex.: lágrima inchando no canto do olho).
    `layer`: "back" desenha atrás dos olhos, "front" na frente.
    """

    kind: str
    x: float
    y: float
    size: float
    life: float
    color: Color = (255.0, 255.0, 255.0)
    vx: float = 0.0
    vy: float = 0.0
    ay: float = 0.0
    size_x: Optional[float] = None  # tamanho horizontal em larguras de olho (anéis); None = proporcional
    angle: float = 0.0
    spin: float = 0.0
    hold: float = 0.0
    fade_in: float = 0.1
    fade_out: float = 0.3
    phase: float = 0.0
    layer: str = "front"
    age: float = 0.0

    @property
    def alive(self) -> bool:
        return self.age < self.life

    @property
    def progress(self) -> float:
        return clamp(self.age / self.life) if self.life > 0 else 1.0

    @property
    def grow(self) -> float:
        """0 -> 1 durante o `hold` (nascimento)."""
        return clamp(self.age / self.hold) if self.hold > 0 else 1.0

    @property
    def alpha(self) -> float:
        fade_in = clamp(self.age / self.fade_in) if self.fade_in > 0 else 1.0
        fade_out = clamp((self.life - self.age) / self.fade_out) if self.fade_out > 0 else 1.0
        return min(fade_in, fade_out)

    def release(self, fade: float = 0.35) -> None:
        """Termina em breve com fade, em vez de sumir de uma vez."""
        self.fade_out = fade
        self.life = min(self.life, self.age + fade)

    def update(self, dt: float) -> None:
        self.age += dt
        self.angle += self.spin * dt
        if self.age <= self.hold:
            return
        self.vy += self.ay * dt
        self.x += self.vx * dt
        self.y += self.vy * dt


class ParticleSystem:
    def __init__(self, limit: int = MAX_PARTICLES):
        self.items: List[Particle] = []
        self.limit = limit

    def spawn(self, particle: Particle) -> Particle:
        if len(self.items) >= self.limit:
            self.items.pop(0)
        self.items.append(particle)
        return particle

    def update(self, dt: float) -> None:
        for particle in self.items:
            particle.update(dt)
        self.items = [p for p in self.items if p.alive and -0.5 < p.y < 1.5]

    def count(self, kind: str) -> int:
        return sum(1 for p in self.items if p.kind == kind)

    def clear(self) -> None:
        self.items.clear()


def heartbeat(t: float, period: float = 0.85) -> float:
    """Pulso duplo "tum-tum" em 0..1, repetindo a cada `period` segundos."""
    u = t % period
    return math.exp(-((u / 0.05) ** 2)) + 0.6 * math.exp(-(((u - 0.2) / 0.05) ** 2))
