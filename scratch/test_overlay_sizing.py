import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath("."))
from PyQt6.QtWidgets import QApplication
from ui import ProceduralHUDOverlay
from core.ui_schema import ProceduralUIBuilder, VisualState

app = QApplication.instance() or QApplication(sys.argv)

builder = ProceduralUIBuilder()
builder.add_action_card(
    title="Iniciativa da Evie",
    body="Vejo que está monitorando os tokens no Antigravity IDE essa hora. Precisa de ajuda?",
    actions=[
        {"id": "proactive_action", "label": "✓ Concordo", "style": "success", "payload": {"choice": "Sim, prossiga."}},
        {"id": "proactive_action", "label": "⏱ Mais tarde", "style": "warning", "payload": {"choice": "Mais tarde."}},
        {"id": "proactive_action", "label": "✕ Dispensar", "style": "danger", "payload": {"choice": "Dispensar."}},
    ]
)
payload = builder.build().to_dict()

overlay = ProceduralHUDOverlay()
print("Initial size:", overlay.width(), overlay.height(), "sizeHint:", overlay.sizeHint().width(), overlay.sizeHint().height())

overlay.render_tree(payload["ui_tree"])
print("After render_tree (no adjustSize):", overlay.width(), overlay.height(), "sizeHint:", overlay.sizeHint().width(), overlay.sizeHint().height())

overlay.adjustSize()
print("After adjustSize:", overlay.width(), overlay.height(), "sizeHint:", overlay.sizeHint().width(), overlay.sizeHint().height())
