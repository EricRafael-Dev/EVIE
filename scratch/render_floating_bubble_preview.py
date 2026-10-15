import sys
import os
sys.path.insert(0, os.path.abspath("."))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QRectF
from PyQt6.QtGui import QPainter, QImage, QColor

from ui import PictureInPictureWindow

app = QApplication.instance() or QApplication(sys.argv)

class MockMainWindow:
    _face_path = ""
    class MockHud:
        state = "IDLE"
        speaking = False
        muted = False
        _visual_state = "IDLE_OBSERVING"
    hud = MockHud()
    def showNormal(self): pass
    def activateWindow(self): pass
    def raise_(self): pass

mock_main = MockMainWindow()
pip = PictureInPictureWindow(main_window=mock_main)
pip.resize(160, 160)
pip.move(200, 200)
pip.show()
app.processEvents()

# Exibir fala no balão flutuante
pip.show_speech_bubble("Estou pronta para ajudar você!", duration_sec=10.0)
for _ in range(15):
    pip._bubble._step_fade()
    pip._step()
app.processEvents()

# Canvas combinado: balão acima + pod abaixo
canvas_w = 260
canvas_h = 240
canvas_img = QImage(canvas_w, canvas_h, QImage.Format.Format_ARGB32_Premultiplied)
canvas_img.fill(QColor(14, 20, 27, 255))  # Fundo do desktop simulado

p = QPainter(canvas_img)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

# 1. Renderizar balão de fala acima
bubble_w = pip._bubble.width()
bubble_h = pip._bubble.height()
bubble_x = (canvas_w - bubble_w) // 2
bubble_y = 12

bubble_img = QImage(pip._bubble.size(), QImage.Format.Format_ARGB32_Premultiplied)
bubble_img.fill(Qt.GlobalColor.transparent)
bp = QPainter(bubble_img)
pip._bubble.render(bp)
bp.end()
p.drawImage(bubble_x, bubble_y, bubble_img)

# 2. Renderizar pod do PiP logo abaixo do balão
pip_w = pip.width()
pip_h = pip.height()
pip_x = (canvas_w - pip_w) // 2
pip_y = bubble_y + bubble_h + 8

pip_img = QImage(pip.size(), QImage.Format.Format_ARGB32_Premultiplied)
pip_img.fill(Qt.GlobalColor.transparent)
pp = QPainter(pip_img)
pip.render(pp)
pp.end()
p.drawImage(pip_x, pip_y, pip_img)

p.end()

artifact_path = "C:/Users/Rafael/.gemini/antigravity-ide/brain/b2fb07bd-271f-401b-95d5-f1e1d9c326d4/pip_floating_bubble_preview.png"
canvas_img.save(artifact_path)
print(f"Saved floating speech bubble preview to {artifact_path}")
