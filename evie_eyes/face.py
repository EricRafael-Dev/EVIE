"""Face: dois olhos, molas de pose e camadas procedurais."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from .behaviors.blink import BlinkLayer
from .behaviors.breathing import BreathingLayer, DriftLayer
from .behaviors.dance import DanceLayer
from .behaviors.emotion import GlyphPulseLayer, HopLayer, TrembleLayer
from .behaviors.saccade import SaccadeLayer
from .behaviors.yawn import YawnLayer
from .core.spring import Spring
from .effects.emotion import EmotionFX, validate_fx
from .effects.particles import Particle
from .model.params import DEFAULT_COLOR, NUMERIC_FIELDS, EyeParams
from .model.presets import Preset, load_presets
from .states.idle import IdleConfig, IdleController

# (frequência Hz, amortecimento) por parâmetro: valores < 1 geram overshoot suave.
POSE_SPRINGS: Dict[str, Tuple[float, float]] = {
    "w": (4.0, 0.7),
    "h": (4.5, 0.55),
    "radius": (4.0, 1.0),
    "x": (5.0, 0.8),
    "y": (5.0, 0.8),
    "lid_top": (5.0, 0.7),
    "lid_tilt": (5.0, 0.7),
    "lid_bottom": (5.0, 0.7),
    "arc": (4.0, 0.75),
    "glow": (3.0, 1.0),
    "highlight": (4.0, 1.0),
    "shade": (3.0, 1.0),
    "blush": (2.0, 1.0),
    "tremble": (3.0, 1.0),
    "wet": (1.5, 1.0),
}
COLOR_RATE = 6.0  # 1/s, suavização exponencial da cor
BLINK_CUT_ARC = 0.3  # mudança de `arc` acima disso troca a forma escondida num piscar
BLINK_CUT_CLOSURE = 0.9  # quão fechado o olho precisa estar para trocar a forma


class Face:
    def __init__(
        self,
        seed: Optional[int] = None,
        presets: Optional[Dict[str, Preset]] = None,
        idle_config: Optional[IdleConfig] = None,
    ):
        self.rng = random.Random(seed)
        self.presets = presets if presets is not None else load_presets()
        self.expression = "neutral"
        self.time = 0.0
        self._revert_in: Optional[float] = None
        self._pending: Optional[List[EyeParams]] = None

        self._targets: List[EyeParams] = self._preset_targets("neutral")
        self._pose: List[EyeParams] = [t.copy() for t in self._targets]
        self._springs: List[Dict[str, Spring]] = [
            {name: Spring(getattr(p, name), *POSE_SPRINGS[name]) for name in NUMERIC_FIELDS}
            for p in self._pose
        ]

        self.saccade = SaccadeLayer(self.rng, on_shift=self._on_saccade)
        self.drift = DriftLayer(self.rng)
        self.breathing = BreathingLayer(self.rng)
        self.tremble = TrembleLayer(self.rng)
        self.hop = HopLayer()
        self.glyph = GlyphPulseLayer()
        self.yawn = YawnLayer(on_finish=lambda: self.blink.trigger(slow=True))
        self.dance = DanceLayer(self)
        self.blink = BlinkLayer(self.rng)
        # O piscar vem por último porque multiplica a altura já composta.
        self.layers = [
            self.saccade, self.drift, self.breathing, self.tremble, self.hop, self.glyph, self.yawn, self.dance, self.blink,
        ]

        for preset in self.presets.values():
            validate_fx(preset.name, preset.fx)
        self.fx = EmotionFX(self, self.rng)
        self.idle = IdleController(self, idle_config or IdleConfig(), self.rng)
        self.eyes: Tuple[EyeParams, EyeParams] = (self._pose[0].copy(), self._pose[1].copy())

    @property
    def particles(self) -> List[Particle]:
        """Partículas vivas (lágrimas, Zzz, brilhos...) para passar ao renderer."""
        return self.fx.particles.items

    # --- API pública -------------------------------------------------------

    def set_expression(self, name: str, duration: Optional[float] = None, *, source: str = "user") -> None:
        """Troca a expressão base. Com `duration`, volta a "neutral" depois."""
        if name not in self.presets:
            raise ValueError(f"Expressão desconhecida {name!r}. Disponíveis: {sorted(self.presets)}")
        if source == "idle" and ((self._revert_in is not None and self._revert_in > 0) or getattr(self.dance, "dancing", False)):
            return
        if source == "user" or name in ("happy", "love", "wink", "surprised", "excited", "sad", "angry"):
            self.idle.reset()
        if getattr(self.dance, "dancing", False) and name != "happy":
            self.dance.stop()

        old_name = self.expression
        self.expression = name
        self._revert_in = duration
        if name == "asleep":
            self.saccade.enabled = False
            self.blink.enabled = False
        elif old_name == "asleep" and name != "asleep":
            self.saccade.enabled = True
            self.blink.enabled = True

        targets = self._preset_targets(name)
        if any(t.arc > 0.05 for t in targets):
            # Olhos felizes em arco (^ ^): limpa qualquer resquício de pálpebra de tédio/sono
            for t in targets:
                t.lid_top = 0.0
                t.lid_bottom = 0.0
                t.lid_tilt = 0.0
            for springs, pose in zip(self._springs, self._pose):
                pose.lid_top = 0.0
                pose.lid_bottom = 0.0
                pose.lid_tilt = 0.0
                if "lid_top" in springs:
                    springs["lid_top"].snap(0.0)
                if "lid_bottom" in springs:
                    springs["lid_bottom"].snap(0.0)
                if "lid_tilt" in springs:
                    springs["lid_tilt"].snap(0.0)
        elif any(t.lid_top > 0.05 for t in targets):
            # Olhos com pálpebra (sono/tristeza): limpa qualquer resquício de arco
            for t in targets:
                t.arc = 0.0
            for springs, pose in zip(self._springs, self._pose):
                pose.arc = 0.0
                if "arc" in springs:
                    springs["arc"].snap(0.0)

        # Se havia uma transição pendente sendo interrompida, descarta o alvo antigo
        self._pending = None

        self._targets = targets
        if any(abs(t.arc - p.arc) > BLINK_CUT_ARC or t.glyph != p.glyph for t, p in zip(targets, self._pose)):
            # Morph de forma grande (ex.: quadrado -> ^ ou -> coração): troca com o olho fechado
            self._pending = targets
            self.blink.trigger()
        else:
            self._pending = None
        self.fx.on_expression(self.presets[name].fx)

    def look_at(self, x: float, y: float, hold: float = 2.0) -> None:
        """Olha para (x, y) em -1..1 durante `hold` segundos. Ignorado se estiver dormindo."""
        if self.idle.stage == "asleep":
            return
        self.idle.reset()
        self.saccade.look_at(x, y, hold)

    def track_gaze(self, x: float, y: float) -> None:
        """Rastreia continuamente uma coordenada de olhar (ex.: cursor do mouse)."""
        if self.idle.stage == "asleep":
            return
        self.saccade.track(x, y)

    def stop_tracking_gaze(self) -> None:
        """Retorna ao modo de sacadas autônomas."""
        self.saccade.stop_tracking()

    def trigger_dance(self, duration: float = 4.5) -> None:
        """Inicia animação de dança com olhos felizes (^ ^), saltitando e balançando de um lado para o outro."""
        self.dance.trigger(duration)

    def trigger_wink(self, eye: str = "left") -> None:
        """Pisca o olho esquerdo ou direito individualmente."""
        expr = "wink_left" if eye == "left" else "wink_right"
        if expr in self.presets:
            self.set_expression(expr, duration=1.8)
        else:
            self.set_expression("wink", duration=1.8)

    def set_custom_color(self, color: Optional[Tuple[float, float, float]]) -> None:
        """Define uma cor dinâmica global (ex.: verde vibrante ao escutar). None restaura o padrão."""
        self._custom_color = color
        for t in self._targets:
            t.color = color if color is not None else DEFAULT_COLOR

    def blink_now(self, double: bool = False) -> None:
        self.blink.trigger(double=double)

    def poke(self) -> None:
        """Estímulo genérico: acorda se estiver dormindo e zera o tédio."""
        self.idle.wake()

    def snap(self) -> None:
        """Pula direto para a pose alvo (sem animação)."""
        if self._pending is not None:
            self._targets, self._pending = self._pending, None
            self.blink.cancel()
        self._snap_pose()

    def update(self, dt: float) -> None:
        self.time += dt
        if self._revert_in is not None:
            self._revert_in -= dt
            if self._revert_in <= 0.0:
                self.set_expression("neutral", source="idle")

        self.idle.update(dt)
        self._update_pose(dt)
        for layer in self.layers:
            layer.update(dt)
        if self._pending is not None and (self.blink.closure >= BLINK_CUT_CLOSURE or not self.blink.blinking):
            self._targets, self._pending = self._pending, None
            self._snap_pose()

        left, right = self._pose[0].copy(), self._pose[1].copy()
        for layer in self.layers:
            layer.apply(left, right)
        self.eyes = (left, right)
        self.fx.update(dt)

    # --- internos ----------------------------------------------------------

    def _snap_pose(self) -> None:
        self._pose = [t.copy() for t in self._targets]
        for springs, pose in zip(self._springs, self._pose):
            for name, spring in springs.items():
                spring.snap(getattr(pose, name))

    def _preset_targets(self, name: str) -> List[EyeParams]:
        preset = self.presets[name]
        targets = [preset.left.copy(), preset.right.copy()]
        custom = getattr(self, "_custom_color", None)
        if custom is not None and not getattr(preset.left, "_explicit_color", False):
            for t in targets:
                t.color = custom
        return targets

    def _update_pose(self, dt: float) -> None:
        k = 1.0 - math.exp(-COLOR_RATE * dt)
        for pose, target, springs in zip(self._pose, self._targets, self._springs):
            for name, spring in springs.items():
                spring.target = getattr(target, name)
                setattr(pose, name, spring.update(dt))
            pose.color = tuple(c + (t - c) * k for c, t in zip(pose.color, target.color))  # type: ignore[assignment]

    def _on_saccade(self, distance: float) -> None:
        # Olhadas grandes costumam vir acompanhadas de uma piscada.
        if distance > 0.5 and self.rng.random() < 0.3 and not self.blink.blinking:
            self.blink.trigger()
