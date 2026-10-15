import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath("."))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QColor
from ui import ProceduralHUDOverlay
from core.ui_schema import ProceduralUIBuilder, VisualState

app = QApplication.instance() or QApplication(sys.argv)

text = "Vejo que está monitorando os tokens no Antigravity IDE essa hora. Precisa de ajuda com alguma otimização no Mark-LV?"
builder = ProceduralUIBuilder(visual_state=VisualState.CURIOUS_SPARK, voice_text=text)
builder.add_action_card(
    title="Iniciativa da Evie",
    body=text,
    actions=[
        {"id": "proactive_action", "label": "✓ Concordo", "style": "success", "payload": {"choice": "Sim, prossiga."}},
        {"id": "proactive_action", "label": "⏱ Mais tarde", "style": "warning", "payload": {"choice": "Mais tarde."}},
        {"id": "proactive_action", "label": "✕ Dispensar", "style": "danger", "payload": {"choice": "Dispensar."}},
    ]
)
payload = builder.build().to_dict()

overlay = ProceduralHUDOverlay()
overlay.render_tree(payload["ui_tree"])
overlay.adjustSize()

pm = QPixmap(overlay.size())
pm.fill(QColor(0, 0, 0, 0))
overlay.render(pm)
pm.save("scratch/overlay_before.png")
print("Saved scratch/overlay_before.png, size:", overlay.width(), overlay.height())
