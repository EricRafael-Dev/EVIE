"""
Holographic Astrolabe / Data-Sphere avatar for the HUD centre.
Clean, breathable, and well-spaced cybernetic holographic sphere:
- Clean, uncluttered layout with tracks placed well away from the glowing core.
- Crisp, airy orbital rings and delicate circuit paths with enhanced transparency / opacity balance.
- Clear distinction between the central luminous core and the outer shell.
- Fully animated in 3D: smooth continuous rotation, reacting to voice amplitude and glance.
"""

from __future__ import annotations

import math
import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient


def _c(col: QColor, a: float) -> QColor:
    """Copy of `col` at alpha `a` (0-255, clamped)."""
    q = QColor(col)
    q.setAlpha(int(max(0.0, min(255.0, a))))
    return q


def _blend(bg: QColor, col: QColor, a: float) -> QColor:
    """col at alpha a pre-mixed onto bg, returned opaque for fast raster rendering."""
    f = max(0.0, min(1.0, a / 255.0))
    return QColor(
        int(bg.red() + (col.red() - bg.red()) * f),
        int(bg.green() + (col.green() - bg.green()) * f),
        int(bg.blue() + (col.blue() - bg.blue()) * f),
    )


class WireframeHoloAvatar:
    """Animated Holographic Astrolabe Sphere Core — Clean & Spaced."""

    SPAN = 1.90
    shaded = True

    def __init__(self) -> None:
        self._t = 0.0
        self._yaw = 0.0
        self._pitch = 0.0
        self._roll = 0.0
        self._amp = 0.0
        self._glow = 0.0
        self._speaking = False
        self._muted = False
        self._state = "IDLE"
        self._visual_state = "IDLE_OBSERVING"
        self._turbulence = 0.2
        self._energy_phase = 0.0

        # VisualState Palettes: (primary_hex, accent_hex)
        self._palettes = {
            "IDLE_OBSERVING": ("#00f0ff", "#00c8ff"),
            "THINKING_DEEP": ("#c084fc", "#a855f7"),
            "CURIOUS_SPARK": ("#f59e0b", "#fbbf24"),
            "SPEAKING": ("#00e676", "#38bdf8"),
            "ALERT_URGENT": ("#ff4d5a", "#ff2a3a"),
            "FOCUS_CALM": ("#38bdf8", "#60a5fa"),
        }

        # Gaze / glance offset
        self._look_x = 0.0
        self._look_y = 0.0
        self._look_tgt_x = 0.0
        self._look_tgt_y = 0.0
        self._look_timer = 0.0

        rng = np.random.RandomState(2024)

        # 1. Clean, spaced rectilinear circuit paths on the outer spherical shell
        # Keeping radius strictly away from the core (> 0.82 to 1.12)
        self._circuits = []
        n_circuits = 55  # Clean & selective
        for _ in range(n_circuits):
            pts = []
            r_layer = rng.uniform(0.85, 1.10)
            lat = rng.uniform(-math.pi * 0.42, math.pi * 0.42)
            lon = rng.uniform(0, 2 * math.pi)
            
            steps = rng.randint(3, 7)
            for _ in range(steps):
                x = r_layer * math.cos(lat) * math.cos(lon)
                y = r_layer * math.sin(lat)
                z = r_layer * math.cos(lat) * math.sin(lon)
                pts.append((x, y, z))

                if rng.rand() > 0.5:
                    lon += rng.choice([-0.24, -0.14, 0.14, 0.24])
                else:
                    d_lat = rng.choice([-0.18, -0.10, 0.10, 0.18])
                    lat = np.clip(lat + d_lat, -math.pi * 0.44, math.pi * 0.44)
            
            self._circuits.append({
                "pts": np.array(pts, dtype=np.float32),
                "bright": rng.uniform(0.55, 1.0),
                "width": 1.1 if rng.rand() > 0.3 else 1.4,
                "has_tick": rng.rand() > 0.4,
            })

        # 2. Outer Orbital Rings & Gimbal Circles (airy, well-defined)
        self._outer_rings = []
        outer_configs = [
            # (radius, normal_vector, speed, width, brightness)
            (0.86, [0.25, 0.92, -0.25], -0.35, 1.2, 0.85),
            (0.96, [-0.65, 0.35, 0.65], 0.30, 1.3, 0.80),
            (1.04, [0.0, 1.0, 0.0], 0.22, 1.3, 0.90),      # Equator
            (1.10, [0.85, 0.15, -0.45], -0.20, 1.2, 0.75),
            (1.18, [-0.5, 0.7, 0.5], 0.16, 1.1, 0.70),
        ]
        for r_rad, norm_vec, spd, w_val, brt in outer_configs:
            n = np.array(norm_vec, dtype=np.float32)
            n /= np.linalg.norm(n)
            arb = np.array([0.0, 1.0, 0.0] if abs(n[1]) < 0.9 else [1.0, 0.0, 0.0], dtype=np.float32)
            u = np.cross(n, arb)
            u /= np.linalg.norm(u)
            v = np.cross(n, u)
            self._outer_rings.append({
                "u": u, "v": v, "r": r_rad,
                "speed": spd, "width": w_val, "bright": brt, "segs": 96
            })

        # 3. Dedicated Inner Core Rings (spaced, elegant, not overcrowded)
        self._inner_rings = []
        inner_configs = [
            # (radius, normal_vector, speed, width, brightness, segs, dotted)
            (0.18, [0.1, 0.95, 0.2], 1.8, 1.3, 0.95, 48, False),
            (0.26, [-0.4, 0.85, 0.3], -1.4, 1.2, 0.90, 60, True),
            (0.35, [0.7, 0.3, 0.6], 1.1, 1.3, 0.85, 72, False),
            (0.46, [-0.2, 0.96, -0.15], -0.8, 1.2, 0.80, 84, True),
        ]
        for r_rad, norm_vec, spd, w_val, brt, segs, dotted in inner_configs:
            n = np.array(norm_vec, dtype=np.float32)
            n /= np.linalg.norm(n)
            arb = np.array([0.0, 1.0, 0.0] if abs(n[1]) < 0.9 else [1.0, 0.0, 0.0], dtype=np.float32)
            u = np.cross(n, arb)
            u /= np.linalg.norm(u)
            v = np.cross(n, u)
            self._inner_rings.append({
                "u": u, "v": v, "r": r_rad,
                "speed": spd, "width": w_val, "bright": brt, "segs": segs, "dotted": dotted
            })

        # 4. Refined Data Pins / Nodes (cleanly distributed on outer shell)
        n_dots = 75  # Reduced from 190 for a clean, readable aesthetic
        r_dots = rng.uniform(0.85, 1.12, n_dots)
        th_dots = rng.uniform(0, 2 * math.pi, n_dots)
        ph_dots = np.arccos(rng.uniform(-0.94, 0.94, n_dots))
        dx = r_dots * np.sin(ph_dots) * np.cos(th_dots)
        dy = r_dots * np.cos(ph_dots)
        dz = r_dots * np.sin(ph_dots) * np.sin(th_dots)
        self._dots = np.stack([dx, dy, dz], axis=1).astype(np.float32)
        self._dot_sizes = rng.uniform(1.2, 2.5, n_dots).astype(np.float32)
        self._dot_styles = rng.choice([0, 1, 2], n_dots, p=[0.65, 0.25, 0.10])

        # 5. Spherical Wireframe Cage (4 clean parallels)
        self._latitudes = []
        for lat_deg in (-55, -25, 25, 55):
            phi = math.radians(90 - lat_deg)
            r_lat = math.sin(phi)
            y_lat = math.cos(phi)
            pts = []
            for deg in range(0, 365, 10):
                th = math.radians(deg)
                pts.append((r_lat * math.cos(th), y_lat, r_lat * math.sin(th)))
            self._latitudes.append(np.array(pts, dtype=np.float32))

    def set_visual_state(self, state: str) -> None:
        """Set procedural visual state (IDLE_OBSERVING, THINKING_DEEP, CURIOUS_SPARK, SPEAKING, ALERT_URGENT, FOCUS_CALM)."""
        st = (state or "").upper()
        if st in self._palettes:
            self._visual_state = st
            if st == "ALERT_URGENT":
                self._turbulence = 0.85
            elif st == "THINKING_DEEP":
                self._turbulence = 0.60
            elif st == "CURIOUS_SPARK":
                self._turbulence = 0.40
            elif st == "SPEAKING":
                self._turbulence = 0.30
            elif st == "FOCUS_CALM":
                self._turbulence = 0.05
            else:
                self._turbulence = 0.15

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Subtly tilt or orient the astrolabe sphere towards a target."""
        self._look_tgt_x = max(-0.35, min(0.35, dx * 0.25))
        self._look_tgt_y = max(-0.35, min(0.35, dy * 0.25))
        self._look_timer = hold

    def step(self, dt: float, amp: float, speaking: bool = False,
             muted: bool = False, state: str = "",
             v_open: float | None = None, v_wide: float = 0.0,
             v_level: float | None = None,
             v_seq: list | None = None, v_hop: float = 0.02) -> None:
        """Advance the rotation and energy animation."""
        dt = max(0.001, min(0.10, float(dt)))
        self._t += dt
        self._amp = max(0.0, min(1.0, float(amp)))
        self._speaking = speaking
        self._muted = muted
        self._state = state or "IDLE"

        # Energy reaction
        tgt_glow = (0.35 + self._amp * 0.65) if (speaking or self._amp > 0.04) else 0.12
        if self._visual_state in ("THINKING_DEEP", "ALERT_URGENT") or state in ("THINKING", "PROCESSING"):
            tgt_glow = max(tgt_glow, 0.65)
        self._glow += (tgt_glow - self._glow) * (1.0 - math.exp(-dt / 0.07))

        # Rotational speed based on visual state and physics
        rot_mult = 1.0
        if self._visual_state == "ALERT_URGENT":
            rot_mult = 3.0
        elif self._visual_state == "THINKING_DEEP" or state in ("THINKING", "PROCESSING"):
            rot_mult = 2.2
        elif self._visual_state == "CURIOUS_SPARK":
            rot_mult = 1.6
        elif speaking or self._visual_state == "SPEAKING":
            rot_mult = 1.3 + self._amp * 0.9
        elif self._visual_state == "FOCUS_CALM":
            rot_mult = 0.5
        elif muted:
            rot_mult = 0.4

        self._energy_phase += dt * rot_mult
        self._yaw += dt * 0.20 * rot_mult
        # Add turbulence wobble to pitch and roll
        turb_wobble = self._turbulence * 0.15 * math.sin(self._energy_phase * 1.8)
        self._pitch = 0.20 * math.sin(self._energy_phase * 0.24) + turb_wobble
        self._roll = 0.10 * math.cos(self._energy_phase * 0.16) + (turb_wobble * 0.5)

        # Glance interpolation
        if self._look_timer > 0.0:
            self._look_timer -= dt
            if self._look_timer <= 0.0:
                self._look_tgt_x = 0.0
                self._look_tgt_y = 0.0
        self._look_x += (self._look_tgt_x - self._look_x) * (1.0 - math.exp(-dt / 0.12))
        self._look_y += (self._look_tgt_y - self._look_y) * (1.0 - math.exp(-dt / 0.12))

    def _get_rotation_matrix(self) -> np.ndarray:
        """Calculate 3D rotation matrix."""
        y = self._yaw + self._look_x
        p = self._pitch + self._look_y
        r = self._roll

        cy, sy = math.cos(y), math.sin(y)
        cp, sp = math.cos(p), math.sin(p)
        cr, sr = math.cos(r), math.sin(r)

        Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
        Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], dtype=np.float32)
        Rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]], dtype=np.float32)
        return Ry @ Rx @ Rz

    def paint(self, p: QPainter, cx: float, cy: float, r: float,
              primary: QColor, accent: QColor, bg: QColor | None = None) -> None:
        """Draw the holographic data sphere."""
        if bg is None:
            bg = QColor(0, 0, 0)

        # Apply procedural visual state palette if active
        if self._visual_state in self._palettes:
            pri_hex, acc_hex = self._palettes[self._visual_state]
            primary = QColor(pri_hex)
            accent = QColor(acc_hex)

        R = r * 0.96
        amp = self._amp
        glow = self._glow
        t = self._energy_phase
        Rmat = self._get_rotation_matrix()
        cam_d = 4.4

        def project(pts3d: np.ndarray):
            """Project 3D points [N, 3] to screen."""
            rot = pts3d @ Rmat.T
            z = rot[:, 2]
            w = np.maximum(cam_d - z, 0.4)
            k = (cam_d / w) * R
            xs = cx + rot[:, 0] * k
            ys = cy - rot[:, 1] * k
            df = np.clip((z + 1.2) / 2.4, 0.08, 1.0)
            return xs, ys, df, z

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # ── 1. BACKGROUND GLOW AURA (Subtle, clean atmosphere) ────────────────
        aura_r = R * 1.12
        g_aura = QRadialGradient(cx, cy, aura_r)
        g_aura.setColorAt(0.00, _blend(bg, primary, int(25 + 40 * glow)))
        g_aura.setColorAt(0.35, _blend(bg, primary, int(12 + 18 * glow)))
        g_aura.setColorAt(0.75, _blend(bg, primary, int(3 + 5 * glow)))
        g_aura.setColorAt(1.00, _blend(bg, primary, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g_aura))
        p.drawEllipse(QRectF(cx - aura_r, cy - aura_r, aura_r * 2, aura_r * 2))

        # ── 2. LATITUDE PARALLELS (Thin wireframe sphere grid) ───────────────
        for lat_pts in self._latitudes:
            xs, ys, dfs, zs = project(lat_pts)
            for i in range(len(lat_pts) - 1):
                avg_z = (zs[i] + zs[i+1]) * 0.5
                avg_df = (dfs[i] + dfs[i+1]) * 0.5
                # Crisp opacity: solid front, dimmed back
                a = int((30 + 80 * avg_df) * (0.85 if avg_z > 0 else 0.35))
                p.setPen(QPen(_blend(bg, primary, a), 0.8))
                p.drawLine(QLineF(xs[i], ys[i], xs[i+1], ys[i+1]))

        # ── 3. RECTILINEAR CIRCUIT TRACKS (Outer shell, spaced from center) ──
        for circ in self._circuits:
            pts = circ["pts"]
            xs, ys, dfs, zs = project(pts)
            bright = circ["bright"]
            wid = circ["width"]
            for i in range(len(pts) - 1):
                avg_z = (zs[i] + zs[i+1]) * 0.5
                avg_df = (dfs[i] + dfs[i+1]) * 0.5
                
                # Higher opacity & contrast for clarity
                a = int((60 + 195 * avg_df) * bright * (1.0 if avg_z > -0.1 else 0.45))
                
                pulse = math.sin(t * 3.5 + float(pts[0, 0]) * 15.0 + i * 0.8)
                if pulse > 0.70 and avg_z > -0.2:
                    col = _blend(bg, accent, min(255, a + 60))
                    w_draw = wid + 0.4
                else:
                    col = _blend(bg, primary, a)
                    w_draw = wid

                p.setPen(QPen(col, w_draw))
                p.drawLine(QLineF(xs[i], ys[i], xs[i+1], ys[i+1]))

            if circ["has_tick"] and len(pts) > 0 and zs[-1] > -0.3:
                sz = 1.6 + 1.2 * dfs[-1]
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(_blend(bg, primary, int(180 * dfs[-1]))))
                p.drawRect(QRectF(xs[-1] - sz * 0.5, ys[-1] - sz * 0.5, sz, sz))

        # ── 4. OUTER ORBITAL RINGS & GIMBAL ARCS ─────────────────────────────
        for rm in self._outer_rings:
            radius = rm["r"]
            u, v = rm["u"], rm["v"]
            speed, wid, bright, segs = rm["speed"], rm["width"], rm["bright"], rm["segs"]

            ang_offset = t * speed
            step_rad = 2 * math.pi / segs
            pts3d = []
            for i in range(segs + 1):
                ang = i * step_rad + ang_offset
                pts3d.append(radius * (math.cos(ang) * u + math.sin(ang) * v))
            pts3d = np.array(pts3d, dtype=np.float32)

            r_xs, r_ys, r_dfs, r_zs = project(pts3d)

            for i in range(segs):
                avg_z = (r_zs[i] + r_zs[i+1]) * 0.5
                avg_df = (r_dfs[i] + r_dfs[i+1]) * 0.5
                
                # Higher minimum visibility / opacity
                a = (0.35 + 0.65 * avg_df) * bright
                if avg_z < 0:
                    a *= 0.40
                a = min(1.0, a * (1.0 + 0.30 * amp))

                col = _blend(bg, primary, int(a * 255))
                p.setPen(QPen(col, wid if avg_z > 0 else 0.9))
                p.drawLine(QLineF(r_xs[i], r_ys[i], r_xs[i+1], r_ys[i+1]))

                if (i % 24 == 0) and avg_z > -0.2:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(_blend(bg, accent, int(230 * avg_df))))
                    p.drawEllipse(QPointF(r_xs[i], r_ys[i]), 1.6 * avg_df, 1.6 * avg_df)

        # ── 5. LUMINOUS OPTICAL CORE FLARE (Behind inner rings) ──────────────
        flare_r = R * (0.24 + 0.08 * glow + 0.02 * math.sin(t * 2.2))
        g_core = QRadialGradient(cx, cy, flare_r)
        g_core.setColorAt(0.00, _c(QColor(255, 255, 255), int(160 + 80 * glow)))
        g_core.setColorAt(0.25, _c(accent, int(110 + 60 * glow)))
        g_core.setColorAt(0.55, _c(primary, int(40 + 30 * glow)))
        g_core.setColorAt(1.00, _c(primary, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g_core))
        p.drawEllipse(QRectF(cx - flare_r, cy - flare_r, flare_r * 2, flare_r * 2))

        # ── 6. INNER CORE NESTED ORBITAL RINGS ───────────────────────────────
        for rm in self._inner_rings:
            radius = rm["r"]
            u, v = rm["u"], rm["v"]
            speed, wid, bright, segs, dotted = rm["speed"], rm["width"], rm["bright"], rm["segs"], rm["dotted"]

            ang_offset = t * speed
            step_rad = 2 * math.pi / segs
            pts3d = []
            for i in range(segs + 1):
                ang = i * step_rad + ang_offset
                pts3d.append(radius * (math.cos(ang) * u + math.sin(ang) * v))
            pts3d = np.array(pts3d, dtype=np.float32)

            r_xs, r_ys, r_dfs, r_zs = project(pts3d)

            for i in range(segs):
                avg_z = (r_zs[i] + r_zs[i+1]) * 0.5
                avg_df = (r_dfs[i] + r_dfs[i+1]) * 0.5
                
                a = (0.45 + 0.55 * avg_df) * bright
                if avg_z < 0:
                    a *= 0.45
                a = min(1.0, a * (1.0 + 0.40 * amp))

                col = _blend(bg, accent if radius < 0.28 else primary, int(a * 255))
                
                if dotted and (i % 2 == 1):
                    continue

                p.setPen(QPen(col, wid if avg_z > 0 else 0.9))
                p.drawLine(QLineF(r_xs[i], r_ys[i], r_xs[i+1], r_ys[i+1]))

        # ── 7. DATA PINS, NODES & CROSSHAIRS (Outer shell) ───────────────────
        d_xs, d_ys, d_dfs, d_zs = project(self._dots)
        for i in range(len(self._dots)):
            z = d_zs[i]
            df = d_dfs[i]
            style = self._dot_styles[i]
            sz = self._dot_sizes[i] * (0.7 + 0.5 * df)

            if z > -0.4:
                alpha = int((70 + 185 * df) * (1.0 if z > 0 else 0.55))
                col = _blend(bg, accent if (i % 6 == 0) else primary, alpha)

                if style == 0:  # Dot
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(col))
                    p.drawEllipse(QPointF(d_xs[i], d_ys[i]), sz, sz)
                elif style == 1:  # Tiny box
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(col))
                    p.drawRect(QRectF(d_xs[i] - sz, d_ys[i] - sz, sz * 2, sz * 2))
                else:  # Reticle crosshair
                    p.setPen(QPen(col, 1.0))
                    arm = sz * 2.0
                    p.drawLine(QLineF(d_xs[i] - arm, d_ys[i], d_xs[i] + arm, d_ys[i]))
                    p.drawLine(QLineF(d_xs[i], d_ys[i] - arm, d_xs[i], d_ys[i] + arm))

        # ── 8. CENTRAL PINPOINT CORE ─────────────────────────────────────────
        p.setBrush(QBrush(_blend(bg, QColor(255, 255, 255), 255)))
        p.drawEllipse(QRectF(cx - 2.5, cy - 2.5, 5.0, 5.0))
        p.setBrush(QBrush(_c(accent, 140)))
        p.drawEllipse(QRectF(cx - 5.5, cy - 5.5, 11.0, 11.0))


import math
import random
from typing import Optional, Sequence, Tuple
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

try:
    from evie_eyes import Face
    from evie_eyes.render.pygame_backend import FaceRenderer
    from evie_eyes.states.idle import IdleConfig
except ImportError:
    from ..evie_eyes import Face  # type: ignore
    from ..evie_eyes.render.pygame_backend import FaceRenderer  # type: ignore
    from ..evie_eyes.states.idle import IdleConfig  # type: ignore


class EvieEyesAvatar:
    """Motor Procedural Oficial de Olhos Expressivos da Evie (Mark LV - Evie-EYES).

    Renderizador procedural avançado com supersampling 2x (anti-aliasing), bloom em
    duas escalas, vinheta radial de emoção, rastro dinâmico em sacadas rápidas,
    reflexos especulares suaves com paralaxe, gradiente de sombreamento volumétrico,
    arcos expressivos, olhos-símbolo (corações, estrelas) e sistema de partículas
    de emoção completas (lágrimas que incham e caem, Zzz ascendente, brilhos estelares,
    marcas de raiva pulsantes, anel de choque e exclamação).

    Totalmente animado via física de molas (frequência e amortecimento por parâmetro),
    sacadas oculares orgânicas, micro-deriva (ruído 1D), respiração rítmica,
    piscadas simples e duplas, bocejos e máquina de estados de ociosidade/sono.
    """

    SPAN = 1.90
    shaded = True

    def __init__(self, quality: str = "high") -> None:
        self.face = Face()
        self.quality = quality
        self._current_w = 640
        self._current_h = 384
        self.renderer = FaceRenderer(self._current_w, self._current_h, quality=quality)
        
        self._speaking = False
        self._muted = False
        self._visual_state = "IDLE_OBSERVING"
        self._emotion = "neutral"
        self._audio_amp = 0.0
        self._time = 0.0

    # ── Controle de Expressões e Estados Visuais ─────────────────────────────

    def set_expression(self, name: str, duration: Optional[float] = None) -> None:
        """Troca a expressão procedural ativa (neutral, happy, sad, angry, sleepy, asleep,
        surprised, suspicious, wink, love, excited). Com duration, retorna a neutral após o tempo."""
        norm = (name or "neutral").strip().lower()
        if norm in self.face.presets:
            self.face.set_expression(norm, duration=duration)
            self._emotion = norm

    def set_visual_state(self, val: str) -> None:
        """Sincroniza o estado visual do SDUI/Evie com as expressões procedurais."""
        st = str(val or "IDLE_OBSERVING").upper().strip()
        self._visual_state = st
        if st in ("DANCE", "CELEBRATE", "PARTY"):
            self.dance(5.0)
        elif st in ("HAPPY", "JOY"):
            self.set_expression("happy", duration=4.0)
        elif st in ("LOVE", "HEART"):
            self.set_expression("love", duration=4.5)
        elif st in ("EXCITED", "STAR"):
            self.set_expression("excited", duration=4.5)
        elif st in ("SAD",):
            self.set_expression("sad", duration=4.0)
        elif st in ("ANGRY",):
            self.set_expression("angry", duration=4.0)
        elif st in ("WINK", "WINK_LEFT", "WINK_RIGHT"):
            self.set_expression("wink", duration=2.0)
        elif st in ("CURIOUS_SPARK", "CURIOUS"):
            self.set_expression("suspicious", duration=3.5)
            self.face.look_at(0.35, -0.22, hold=2.5)
        elif st in ("THINKING_DEEP", "THINKING"):
            self.face.look_at(0.35, -0.45, hold=3.0)
            # Pensamento é um olhar pensativo para o alto, nunca pálpebras caídas de sono
            if (self.face._revert_in is None or self.face._revert_in <= 0) and not getattr(self.face.dance, "dancing", False):
                if self.face.expression not in ("happy", "love", "excited", "sad", "angry", "wink", "surprised"):
                    self.set_expression("neutral")
        elif st in ("ALERT_URGENT", "SURPRISED"):
            self.set_expression("surprised", duration=3.5)
        elif st in ("FOCUS_CALM", "FOCUSED"):
            self.face.look_at(0.0, 0.0, hold=2.0)
            self.set_expression("neutral")
        elif st in ("SLEEPY", "IDLE_LONG"):
            if (self.face._revert_in is None or self.face._revert_in <= 0) and not getattr(self.face.dance, "dancing", False):
                self.set_expression("sleepy")
        elif st in ("ASLEEP", "SLEEP"):
            if (self.face._revert_in is None or self.face._revert_in <= 0) and not getattr(self.face.dance, "dancing", False):
                self.face.idle.sleep_now()
        elif st in ("SPEAKING",):
            if self.face.idle.stage in ("asleep", "sleepy"):
                self.face.poke()
            # Não zera a expressão se uma emoção ativa (happy, love, etc.) estiver em andamento
        elif st in ("IDLE_OBSERVING", "NEUTRAL"):
            if not getattr(self.face.dance, "dancing", False):
                if self.face._revert_in is not None and self.face._revert_in <= 0:
                    self.set_expression("neutral")
                elif self.face._revert_in is None and self.face.expression not in ("love", "excited", "sad", "angry"):
                    self.set_expression("neutral")

    def set_emotion(self, emotion: str) -> None:
        norm = str(emotion or "neutral").lower().strip()
        if norm in self.face.presets:
            self.set_expression(norm)
        else:
            self.set_visual_state(emotion)

    def set_speaking(self, val: bool) -> None:
        self._speaking = bool(val)
        if self._speaking:
            if self.face.idle.stage in ("asleep", "sleepy"):
                self.face.poke()

    def set_muted(self, val: bool) -> None:
        self._muted = bool(val)
        if self._muted:
            self.set_expression("sleepy")
        else:
            self.set_expression("neutral")

    def set_state(self, val: str) -> None:
        self.set_visual_state(val)

    # ── Ações e Interações ───────────────────────────────────────────────────

    def glance(self, dx: float, dy: float, hold: float = 1.2) -> None:
        """Direciona o olhar orgânico para (dx, dy) em -1..1 por `hold` segundos."""
        self.face.look_at(dx, dy, hold=hold)

    def look_at(self, x: float, y: float, hold: float = 2.0) -> None:
        self.face.look_at(x, y, hold=hold)

    def track_gaze(self, x: float, y: float) -> None:
        """Rastreamento contínuo de olhar (ex.: mouse/cursor em tempo real no Windows/Desktop)."""
        if hasattr(self.face, "track_gaze"):
            self.face.track_gaze(x, y)
        else:
            self.face.look_at(x, y, hold=2.0)

    def stop_tracking_gaze(self) -> None:
        """Retorna suavemente às sacadas e olhar autônomo."""
        if hasattr(self.face, "stop_tracking_gaze"):
            self.face.stop_tracking_gaze()

    def trigger_wink(self, eye: str = "left") -> None:
        expr = "wink_left" if eye == "left" else "wink_right"
        if hasattr(self, "face") and hasattr(self.face, "presets") and expr in self.face.presets:
            self.set_expression(expr, duration=1.8)
        else:
            self.set_expression("wink", duration=1.8)

    def trigger_happy(self, duration: float = 2.0) -> None:
        self.set_expression("happy", duration=duration)

    def trigger_dance(self, duration: float = 4.5) -> None:
        """Dispara animação de dança com olhos felizes (^ ^), saltitando e balançando de um lado para o outro."""
        if hasattr(self.face, "trigger_dance"):
            self.face.trigger_dance(duration)

    def dance(self, duration: float = 4.5) -> None:
        self.trigger_dance(duration)

    def blink_now(self, double: bool = False) -> None:
        self.face.blink_now(double=double)

    def hop(self, strength: float = 1.0) -> None:
        """Pulinho elástico nos olhos (HopLayer) com amortecimento suave."""
        if hasattr(self, "face") and hasattr(self.face, "hop"):
            self.face.hop.kick(strength)

    def poke(self) -> None:
        """Cutuca/interage com a Evie: acorda se estiver dormindo e zera o tédio."""
        self.face.poke()

    def yawn(self) -> None:
        """Dispara animação de bocejo com estiramento e piscar subsequente."""
        self.face.yawn.trigger()

    def sleep(self) -> None:
        """Põe a Evie para dormir imediatamente com Zzz ascendente."""
        self.face.idle.sleep_now()

    def wake(self) -> None:
        self.face.poke()

    def snap(self) -> None:
        self.face.snap()

    # ── Ciclo de Atualização e Renderização ──────────────────────────────────

    def step(self, dt: float, amp: float = 0.0, **kwargs) -> None:
        """Avança a simulação física com o delta de tempo dt e a amplitude do áudio."""
        self._time += dt
        self._audio_amp = max(0.0, min(1.0, float(amp)))

        speaking = kwargs.get("speaking", self._speaking)
        muted = kwargs.get("muted", self._muted)
        state = kwargs.get("state", None)

        if speaking != self._speaking:
            self.set_speaking(speaking)
        if muted != self._muted:
            self.set_muted(muted)

        # Transições de estado operacional sem sobrescrever emoções ativas
        if state and self.face.expression == "neutral":
            if state in ("THINKING", "PROCESSING"):
                self.face.look_at(0.45, -0.55, hold=2.0)
            elif state == "MUTED":
                self.set_expression("sleepy")

        # Reatividade dinâmica da voz: respiração viva e dilatação proporcional ao áudio
        if self._speaking:
            # Período de respiração diminui (mais rápida e vívida) conforme a fala
            self.face.breathing.period = max(1.3, 3.6 - self._audio_amp * 2.0)
            self.face.breathing.amplitude = 0.02 + self._audio_amp * 0.025
            self.face.breathing.bob = 0.01 + self._audio_amp * 0.015
            # Em picos de voz, estimula micro-hop e foco visual
            if self._audio_amp > 0.65 and abs(self.face.hop.offset) < 2.0:
                self.face.hop.kick(0.25 * self._audio_amp)
        elif self.face.expression in ("asleep", "sleepy") or (hasattr(self.face, "idle") and self.face.idle.stage in ("asleep", "sleepy")):
            # Respiração profunda e viva durante o sono (evita parecer estática/congelada)
            self.face.breathing.period = 4.8
            self.face.breathing.amplitude = 0.08
            self.face.breathing.bob = 0.045
        else:
            self.face.breathing.reset_defaults()

        self.face.update(dt)
        if self.face.expression == "neutral" and self._emotion != "neutral":
            self._emotion = "neutral"

    def paint(self, p: QPainter, cx: float, cy: float, r: float,
              primary: QColor, accent: QColor, bg: QColor) -> None:
        """Renderiza os olhos procedurais com supersampling, bloom e partículas na tela."""
        target_w = max(110.0, r * 2.70)
        target_h = max(66.0, target_w * (384.0 / 640.0))

        # Resolução procedural nativa travada em 640x384 (proporção 5:3)
        # Garante render procedural ultra rápido (< 1.2ms) em qualquer máquina,
        # escalado suavemente com SmoothPixmapTransform para qualquer viewport.
        if (self._current_w, self._current_h) != (640, 384):
            self._current_w = 640
            self._current_h = 384
            self.renderer.resize(640, 384)

        if bg and hasattr(self.renderer, "bg"):
            rgb_bg = (bg.red(), bg.green(), bg.blue())
            if self.renderer.bg != rgb_bg:
                self.renderer.bg = rgb_bg
                for base in getattr(self.renderer, "_bases", []):
                    base.fill(rgb_bg)
                if hasattr(self.renderer, "_out") and self.renderer._out:
                    self.renderer._out.fill(rgb_bg)

        # Renderização do frame procedural no backend pygame
        surf = self.renderer.render(self.face.eyes, self.face.particles, reuse=True)

        # Conversão do buffer de pixels para QImage ARGB com alpha opaco (0xFF)
        buf = surf.get_buffer()
        raw_qimg = QImage(buf, 640, 384, 640 * 4, QImage.Format.Format_RGB32)
        qimg = raw_qimg.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

        # Desenho no QPainter com suavização bilinear de escala
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        dest_rect = QRectF(cx - target_w / 2.0, cy - target_h / 2.0, target_w, target_h)
        p.drawImage(dest_rect, qimg)
        p.restore()


# Substitui HoloAvatar por EvieEyesAvatar como o motor principal
HoloAvatar = EvieEyesAvatar
__all__ = ["EvieEyesAvatar", "HoloAvatar", "WireframeHoloAvatar"]


