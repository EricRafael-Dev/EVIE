import sys
import os
sys.path.insert(0, os.path.abspath("."))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainter, QImage

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

# 1. Normal state preview
for _ in range(10):
    pip._step()

img = QImage(pip.size(), QImage.Format.Format_ARGB32_Premultiplied)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
pip.render(p)
p.end()

artifact_path = "C:/Users/Rafael/.gemini/antigravity-ide/brain/b2fb07bd-271f-401b-95d5-f1e1d9c326d4/pip_compact_preview.png"
img.save(artifact_path)
print(f"Saved compact PiP preview to {artifact_path}")

# 2. Dragging right -> suspicious_right looking right
pip._handle_press(QPointF(100, 100).toPoint(), QPointF(50, 50).toPoint(), Qt.MouseButton.LeftButton)
pip._handle_move(QPointF(140, 100).toPoint(), Qt.MouseButton.LeftButton)
for _ in range(5):
    pip._step()

img_right = QImage(pip.size(), QImage.Format.Format_ARGB32_Premultiplied)
img_right.fill(Qt.GlobalColor.transparent)
p_right = QPainter(img_right)
pip.render(p_right)
p_right.end()

artifact_right = "C:/Users/Rafael/.gemini/antigravity-ide/brain/b2fb07bd-271f-401b-95d5-f1e1d9c326d4/pip_suspicious_right.png"
img_right.save(artifact_right)
print(f"Saved suspicious_right preview to {artifact_right}")

# 3. Dragging left -> suspicious_left looking left
pip._handle_move(QPointF(60, 100).toPoint(), Qt.MouseButton.LeftButton)
for _ in range(5):
    pip._step()

img_left = QImage(pip.size(), QImage.Format.Format_ARGB32_Premultiplied)
img_left.fill(Qt.GlobalColor.transparent)
p_left = QPainter(img_left)
pip.render(p_left)
p_left.end()

artifact_left = "C:/Users/Rafael/.gemini/antigravity-ide/brain/b2fb07bd-271f-401b-95d5-f1e1d9c326d4/pip_suspicious_left.png"
img_left.save(artifact_left)
print(f"Saved suspicious_left preview to {artifact_left}")

pip._handle_release(QPointF(60, 100).toPoint(), QPointF(30, 50).toPoint(), Qt.MouseButton.LeftButton)

# 4. Asleep mode preview with breathing heave & zzz
pip.set_expression("asleep")
for _ in range(25):
    pip._step()

img_asleep = QImage(pip.size(), QImage.Format.Format_ARGB32_Premultiplied)
img_asleep.fill(Qt.GlobalColor.transparent)
p_asleep = QPainter(img_asleep)
pip.render(p_asleep)
p_asleep.end()

artifact_asleep = "C:/Users/Rafael/.gemini/antigravity-ide/brain/b2fb07bd-271f-401b-95d5-f1e1d9c326d4/pip_asleep_breathing.png"
img_asleep.save(artifact_asleep)
print(f"Saved asleep breathing preview to {artifact_asleep}")
