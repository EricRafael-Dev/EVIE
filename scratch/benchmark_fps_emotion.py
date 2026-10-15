import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
from core.avatar import EvieEyesAvatar
from core.ui_schema import extract_speech_emotion, VisualState
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtGui import QPainter, QPixmap, QColor
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

# 1. Test phrase user mentioned
test_phrases = [
    ("Claro! Estou muito feliz em conversar com você hoje!", VisualState.HAPPY),
    ("Que notícia maravilhosa, eu adorei!", VisualState.HAPPY),
    ("Cuidado, detectei uma falha crítica no sistema!", VisualState.ALERT_URGENT),
    ("Será que podemos testar uma abordagem diferente?", VisualState.CURIOUS_SPARK),
    ("Estou triste com esse acontecimento.", VisualState.SAD),
    ("Isso é inaceitável, que absurdo!", VisualState.ANGRY),
    ("Eu amo quando você me ensina coisas novas!", VisualState.LOVE),
]

for phrase, expected in test_phrases:
    emo = extract_speech_emotion(phrase)
    assert emo == expected, f"Expected {expected} for '{phrase}', got {emo}"
print("[OK] Real-time speech emotion test passed for all phrases!")

# 2. Test persistence during speech
avatar = EvieEyesAvatar()
avatar.set_visual_state("HAPPY")
assert avatar.face.expression == "happy", f"Expression should be happy, got {avatar.face.expression}"

# Simulate 60 steps (1 second) of speaking
for _ in range(60):
    avatar.step(0.016, amp=0.7, speaking=True, state="SPEAKING")
assert avatar.face.expression == "happy", f"Emotion was overwritten during speech! Got {avatar.face.expression}"
print("[OK] Emotion persistence during speech verified (happy expression retained across speech)!")

# 3. Benchmark render performance (FPS)
pm = QPixmap(1280, 720)
pm.fill(QColor("#05070a"))
p = QPainter(pm)

t0 = time.perf_counter()
frames = 120
for _ in range(frames):
    avatar.step(0.016, amp=0.5, speaking=True)
    avatar.paint(p, 640.0, 360.0, 160.0, QColor("#00f0ff"), QColor("#00f0ff"), QColor("#05070a"))
p.end()
t1 = time.perf_counter()
total_ms = (t1 - t0) * 1000
ms_per_frame = total_ms / frames
fps = 1000.0 / ms_per_frame
print(f"[OK] Benchmark: {ms_per_frame:.2f} ms per frame -> {fps:.1f} FPS capability!")
assert fps > 60, f"FPS too low: {fps}"
print("[SUCESSO TOTAL] Todas as validações passaram!")
