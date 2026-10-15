import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath("."))
import time
from PyQt6.QtWidgets import QApplication
from ui import ProceduralHUDOverlay
from core.ui_schema import ProceduralUIBuilder, VisualState

app = QApplication.instance() or QApplication(sys.argv)

text = "Vejo que está monitorando os tokens no Antigravity IDE essa hora. Precisa de ajuda com alguma otimização no Mark-LV?"

builder = ProceduralUIBuilder(
    visual_state=VisualState.CURIOUS_SPARK,
    voice_text=text
)
card_id = f"act_{int(time.time())}"
builder.add_action_card(
    card_id=card_id,
    title="Iniciativa da Evie",
    body=text,
    actions=[
        {"id": "proactive_action", "label": "✓ Concordo", "style": "success", "payload": {"choice": "Sim, prossiga."}},
        {"id": "proactive_action", "label": "⏱ Mais tarde", "style": "warning", "payload": {"choice": "Mais tarde."}},
        {"id": "proactive_action", "label": "✕ Dispensar", "style": "danger", "payload": {"choice": "Dispensar."}},
    ]
)
sdui_payload = builder.build().to_dict()
print("SDUI Payload:")
import json
print(json.dumps(sdui_payload, indent=2, ensure_ascii=False))

overlay = ProceduralHUDOverlay()
overlay.render_tree(sdui_payload["ui_tree"])
overlay.adjustSize()

print(f"\nOverlay size: {overlay.width()} x {overlay.height()}")
print("Rendered widgets in overlay:")
for cid, w in overlay._rendered_widgets.items():
    print(f" - Widget {cid} ({w.__class__.__name__}): size={w.width()}x{w.height()}")
    for child in w.findChildren(object):
        txt = getattr(child, "text", lambda: None)()
        if txt is not None:
            print(f"    - child {child.__class__.__name__}: text={txt!r}")
        else:
            print(f"    - child {child.__class__.__name__}")
