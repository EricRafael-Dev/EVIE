"""Janela interativa: python -m evie_eyes"""
from __future__ import annotations

import argparse
import os
import time
from typing import List, Tuple

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from .face import Face  # noqa: E402
from .loop import AutoQuality, FramePacer, HudText  # noqa: E402
from .model.params import DEFAULT_COLOR  # noqa: E402
from .render.pygame_backend import QUALITY_ORDER, FaceRenderer  # noqa: E402
from .states.idle import IdleConfig  # noqa: E402

STEP = 1.0 / 120.0  # passo da simulação com --fixed-step (animação reprodutível com --seed)
MAX_DT = 0.05       # com passo variável, pausas (arrastar a janela...) não "pulam" a animação além disso
STATUS_INTERVAL = 0.25  # s entre atualizações da linha de status do HUD
HELP = (
    "1-9: expressoes   0: neutral   L: apaixonada   E: empolgada   B/Shift+B: piscar/dupla",
    "Y: bocejar   Z: dormir   Setas: olhar   M: seguir mouse   S: sacadas   D: micro-mov.   R: respiracao",
    "ESPACO: acordar/cutucar   Q: qualidade   H: ajuda   P: screenshot   F11: tela cheia   ESC: sair",
)
COLORS = {
    "cyan": tuple(int(c) for c in DEFAULT_COLOR),
    "green": (100, 235, 140),
    "amber": (255, 190, 80),
    "pink": (255, 120, 200),
}


def parse_fps(value: str) -> float:
    """`--fps`: número (60, 144...), `auto` (taxa de atualização do monitor) ou `0`/`max` (sem limite)."""
    text = value.strip().lower()
    if text == "auto":
        return -1.0
    if text in ("max", "unlimited", "0"):
        return 0.0
    try:
        fps = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"fps inválido: {value!r} (use um número, 'auto' ou 'max')") from None
    if fps < 0:
        raise argparse.ArgumentTypeError("fps não pode ser negativo")
    return fps


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evie_eyes", description="Olhos procedurais animados")
    parser.add_argument("--size", default="800x480", help="tamanho da janela, ex.: 800x480")
    parser.add_argument("--fps", type=parse_fps, default=60.0,
                        help="taxa alvo: número (ex.: 144), 'auto' (taxa do monitor) ou 'max' (sem limite)")
    parser.add_argument("--seed", type=int, default=None, help="seed do aleatório (use com --fixed-step para reprodução exata)")
    parser.add_argument("--color", choices=sorted(COLORS), default="cyan")
    parser.add_argument("--quality", choices=QUALITY_ORDER, default="high", help="custo x beleza do render")
    parser.add_argument("--no-auto-quality", action="store_true",
                        help="não baixa a qualidade sozinho quando o computador não acompanha o --fps")
    parser.add_argument("--fixed-step", action="store_true",
                        help="simulação em passo fixo de 1/120 s (reprodutível, mas pode dar micro-tranco em 144 Hz)")
    parser.add_argument("--fast-idle", action="store_true", help="acelera tédio/bocejo/sono (demo)")
    parser.add_argument("--fullscreen", action="store_true")
    return parser.parse_args(argv)


def resolve_fps(fps: float) -> float:
    """`auto` vira a taxa de atualização do monitor (60 se o pygame não souber)."""
    if fps >= 0:
        return fps
    try:
        rate = pygame.display.get_current_refresh_rate()
    except (AttributeError, pygame.error):
        rate = 0
    return float(rate) if rate and rate > 0 else 60.0


def apply_color(face: Face, color: Tuple[int, int, int]) -> None:
    """Troca a cor base: só afeta presets que não definem cor própria."""
    default = Face(seed=0).presets["neutral"].left.color
    for preset in face.presets.values():
        for eye in (preset.left, preset.right):
            if eye.color == default:
                eye.color = tuple(float(c) for c in color)  # type: ignore[assignment]
    face.set_expression(face.expression, source="idle")
    face.snap()


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv)
    width, height = (int(v) for v in args.size.lower().split("x"))

    pygame.init()
    pygame.display.set_caption("Evie-EYES")
    flags = pygame.RESIZABLE | (pygame.FULLSCREEN if args.fullscreen else 0)
    screen = pygame.display.set_mode((width, height), flags)
    font = pygame.font.Font(None, 22)

    face = Face(seed=args.seed, idle_config=IdleConfig.fast() if args.fast_idle else IdleConfig())
    apply_color(face, COLORS[args.color])
    renderer = FaceRenderer(*screen.get_size(), quality=args.quality)
    keymap = dict(zip((pygame.K_1 + i for i in range(9)), ["happy", "sad", "angry", "sleepy", "surprised", "suspicious", "wink", "asleep", "neutral"]))
    keymap[pygame.K_0] = "neutral"
    keymap[pygame.K_l] = "love"
    keymap[pygame.K_e] = "excited"
    gaze_keys = {
        pygame.K_LEFT: (-0.7, 0.0),
        pygame.K_RIGHT: (0.7, 0.0),
        pygame.K_UP: (0.0, -0.5),
        pygame.K_DOWN: (0.0, 0.5),
    }

    target_fps = resolve_fps(args.fps)
    pacer = FramePacer(target_fps)
    auto_quality = None if args.no_auto_quality or target_fps <= 0 else AutoQuality(target_fps, QUALITY_ORDER)
    hud = HudText(font)
    dt = 1.0 / (target_fps if target_fps > 0 else 60.0)
    accumulator = 0.0
    follow_mouse = False
    show_help = True
    status, status_at, frames_seen, measured_fps, cost_ms = " ", 0.0, 0, 0.0, 0.0
    frame = renderer.render(face.eyes, face.particles, reuse=True)
    running = True
    while running:
        frame_start = time.perf_counter()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                renderer.resize(event.w, event.h)
            elif event.type == pygame.MOUSEMOTION and follow_mouse:
                w, h = screen.get_size()
                face.look_at(event.pos[0] / w * 2 - 1, event.pos[1] / h * 2 - 1, hold=0.4)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in keymap:
                    face.set_expression(keymap[event.key], duration=None if keymap[event.key] in ("neutral", "asleep") else 4.0)
                elif event.key in gaze_keys:
                    face.look_at(*gaze_keys[event.key], hold=1.5)
                elif event.key == pygame.K_b:
                    face.blink_now(double=bool(event.mod & pygame.KMOD_SHIFT))
                elif event.key == pygame.K_y:
                    face.yawn.trigger()
                elif event.key == pygame.K_z:
                    face.idle.sleep_now()
                elif event.key == pygame.K_s:
                    face.saccade.enabled = not face.saccade.enabled
                elif event.key == pygame.K_d:
                    face.drift.enabled = not face.drift.enabled
                elif event.key == pygame.K_r:
                    face.breathing.enabled = not face.breathing.enabled
                elif event.key == pygame.K_q:
                    renderer.set_quality(QUALITY_ORDER[(QUALITY_ORDER.index(renderer.quality) + 1) % len(QUALITY_ORDER)])
                elif event.key == pygame.K_SPACE:
                    face.poke()
                elif event.key == pygame.K_m:
                    follow_mouse = not follow_mouse
                elif event.key == pygame.K_h:
                    show_help = not show_help
                elif event.key == pygame.K_p:
                    path = f"evie_eyes_{int(time.time())}.png"
                    pygame.image.save(frame, path)
                    print(f"Screenshot salvo em {path}")
                elif event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()

        if args.fixed_step:
            accumulator += min(dt, 0.1)
            while accumulator >= STEP:
                face.update(STEP)
                accumulator -= STEP
        else:
            face.update(min(dt, MAX_DT))  # os sub-passos das molas já mantêm a integração estável

        frame = renderer.render(face.eyes, face.particles, reuse=True)
        screen.blit(frame, (0, 0))
        frames_seen += 1
        if frame_start - status_at >= STATUS_INTERVAL:
            measured_fps = frames_seen / max(frame_start - status_at, 1e-6) if status_at else 0.0
            frames_seen, status_at = 0, frame_start
            target = "max" if target_fps <= 0 else f"{target_fps:.0f}"
            status = (
                f"{face.expression} | idle: {face.idle.stage} {face.idle.clock:5.1f}s | qualidade: {renderer.quality}"
                f"{' (auto)' if auto_quality else ''} | {measured_fps:4.0f}/{target} fps | {cost_ms:4.1f} ms/frame"
            )
        lines = ([status] + list(HELP)) if show_help else [status]
        for i, line in enumerate(lines):
            screen.blit(hud.get(line), (10, 8 + i * 20))
        pygame.display.flip()

        elapsed_ms = (time.perf_counter() - frame_start) * 1000.0
        cost_ms = elapsed_ms if not cost_ms else cost_ms * 0.9 + elapsed_ms * 0.1  # média móvel, só para o HUD
        if auto_quality is not None:
            lighter = auto_quality.update(elapsed_ms, renderer.quality)
            if lighter is not None:
                print(f"Qualidade reduzida para '{lighter}': o custo por frame passou do orçamento de {auto_quality.budget_ms:.1f} ms")
                renderer.set_quality(lighter)
        dt = pacer.wait()

    pygame.quit()


if __name__ == "__main__":
    main()
