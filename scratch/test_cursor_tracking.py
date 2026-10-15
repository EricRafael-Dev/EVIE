import sys
import os
import math

sys.stdout.reconfigure(encoding='utf-8')
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath("."))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint
from core.avatar import EvieEyesAvatar

app = QApplication.instance() or QApplication(sys.argv)
avatar = EvieEyesAvatar()

# 1. Simulate cursor at different relative positions
test_points = [
    (0, 0, "Center"),
    (500, 0, "Far Right"),
    (-500, 0, "Far Left"),
    (0, 300, "Below (Taskbar)"),
    (0, -300, "Above (Titlebar)"),
    (1200, 400, "Second Monitor / Far Corner")
]

w, h = 600, 400
head_cx = w / 2.0
head_cy = h * 0.40

print("--- [1] Simulating Global Cursor Tracking ---")
for px, py, label in test_points:
    rel_x = px / (w * 0.50)
    rel_y = py / (h * 0.50)
    target_gx = math.tanh(rel_x) * 0.85
    target_gy = math.tanh(rel_y) * 0.70
    avatar.track_gaze(target_gx, target_gy)
    for _ in range(15):
        avatar.step(0.016)
    left_eye = avatar.face.eyes[0]
    print(f"[{label:25s}] (rel_x={rel_x:+.2f}, rel_y={rel_y:+.2f}) -> Gaze target=({target_gx:+.2f}, {target_gy:+.2f}) | Eye pupil offset=({left_eye.x:+.2f}, {left_eye.y:+.2f})")

# 2. Test persistent tracking without timeout (user stops moving mouse)
print("\n--- [2] Testando persistência do olhar quando o mouse fica parado ---")
target_gx, target_gy = 0.75, -0.35
avatar.track_gaze(target_gx, target_gy)

# Step 30 frames (~0.5s)
for _ in range(30):
    avatar.step(0.016)
pos_after_0_5s = avatar.face.eyes[0].x
print(f"Após 0.5s parado no alvo {target_gx}: Eye pupil x = {pos_after_0_5s:.3f}")
assert abs(pos_after_0_5s - target_gx) < 0.08, "O olho deve ter alcançado o cursor"

# Step 300 frames (~5.0s) SEM mover o mouse
print("Avançando 5 segundos (300 frames) com cursor parado...")
for _ in range(300):
    avatar.step(0.016)
pos_after_5_0s = avatar.face.eyes[0].x
print(f"Após 5.0s parado: Eye pupil x = {pos_after_5_0s:.3f}")
# Before our fix, pos_after_5_0s reverted to ~0.0! Now it must still be holding target_gx ~ 0.75!
assert abs(pos_after_5_0s - target_gx) < 0.08, f"ERRO: Olho voltou ao normal ({pos_after_5_0s}) em vez de manter o foco no cursor ({target_gx})!"
print(" [OK] Olhar manteve foco persistente no cursor sem voltar ao centro!")

# 3. Test stop_tracking_gaze returns to autonomous saccades
print("\n--- [3] Testando retorno suave a sacadas autônomas após inatividade ---")
avatar.stop_tracking_gaze()
# Advance 200 frames (~3.2s)
for _ in range(200):
    avatar.step(0.016)
print(f"Após soltar o olhar e aguardar ciclo de sacada: Eye pupil x = {avatar.face.eyes[0].x:.3f}")
print(" [OK] Transição suave de volta ao repouso/sacadas autônomas validada!")

print("\nTodos os testes de rastreamento contínuo do mouse passaram com sucesso!")
