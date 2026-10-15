"""Gera uma folha de contato PNG com todas as expressões (sem abrir janela).

Uso: python -m evie_eyes.tools.snapshot [--out sheet.png] [--size 480x320]
"""
from __future__ import annotations

import argparse
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from ..face import Face  # noqa: E402
from ..render.pygame_backend import FaceRenderer  # noqa: E402
from ..states.idle import IdleConfig  # noqa: E402


def static_face(expression: str) -> Face:
    """Face com todas as camadas desligadas, para imagens determinísticas."""
    face = Face(seed=0, idle_config=IdleConfig(enabled=False))
    face.set_expression(expression)
    face.snap()
    for layer in (face.saccade, face.drift, face.breathing, face.blink, face.tremble, face.hop, face.glyph):
        layer.enabled = False
    face.update(0.0)
    return face


def build_sheet(size: tuple, columns: int = 3) -> pygame.Surface:
    names = list(Face(seed=0).presets)
    w, h = size
    rows = -(-len(names) // columns)
    sheet = pygame.Surface((w * columns, h * rows))
    renderer = FaceRenderer(w, h)
    font = pygame.font.Font(None, 22)
    for i, name in enumerate(names):
        frame = renderer.render(static_face(name).eyes)
        frame.blit(font.render(name, True, (200, 200, 200)), (8, 6))
        sheet.blit(frame, ((i % columns) * w, (i // columns) * h))
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="expressions.png")
    parser.add_argument("--size", default="480x320")
    args = parser.parse_args()
    w, h = (int(v) for v in args.size.lower().split("x"))
    pygame.init()
    pygame.image.save(build_sheet((w, h)), args.out)
    print(f"Salvo em {args.out}")


if __name__ == "__main__":
    main()
