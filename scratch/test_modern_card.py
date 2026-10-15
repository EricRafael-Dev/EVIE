import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath("."))
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea
)
from PyQt6.QtGui import QFont, QPixmap, QColor
from PyQt6.QtCore import Qt, pyqtSignal

app = QApplication.instance() or QApplication(sys.argv)

class C:
    PRI = "#00f0ff"
    PRI_DIM = "#007a8a"
    ACC = "#ff6b00"
    ACC2 = "#ffaa00"
    BORDER = "#143048"
    TEXT = "#e2f1f8"
    TEXT_MED = "#88b0c8"
    TEXT_DIM = "#4a687c"
    PANEL = "rgba(4, 14, 24, 0.95)"

class ModernActionCard(QFrame):
    def __init__(self, comp: dict, action_signal: pyqtSignal, on_close=None):
        super().__init__()
        data = comp.get("data") or comp
        title = comp.get("title") or data.get("title") or "INICIATIVA DA EVIE"
        body = data.get("description") or data.get("body") or comp.get("body") or comp.get("description") or ""
        actions = data.get("actions") or comp.get("actions") or []

        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(6, 18, 30, 240);
                border: 1px solid #00f0ff;
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # Header with icon and title
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        ico = QLabel("💡")
        ico.setFont(QFont("Segoe UI Emoji", 10))
        ico.setStyleSheet("background: transparent;")
        hdr.addWidget(ico)

        t_lbl = QLabel(title.upper())
        t_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffaa00; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(t_lbl)
        hdr.addStretch()

        if on_close:
            x_btn = QPushButton("✕")
            x_btn.setFixedSize(20, 20)
            x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            x_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            x_btn.setStyleSheet("""
                QPushButton {
                    background: transparent; color: #88b0c8;
                    border: 1px solid #143048; border-radius: 3px;
                }
                QPushButton:hover { color: #ffffff; border-color: #00f0ff; background: rgba(0,240,255,40); }
            """)
            x_btn.clicked.connect(on_close)
            hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        # Body text
        if body:
            b_lbl = QLabel(body)
            b_lbl.setWordWrap(True)
            b_lbl.setFont(QFont("Segoe UI", 10))
            b_lbl.setStyleSheet("color: #e2f1f8; background: transparent; line-height: 140%;")
            lay.addWidget(b_lbl)

        # Buttons row
        if actions:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            for act in actions:
                lbl = act.get("label", "Ação")
                st = act.get("style", "primary").lower()
                btn = QPushButton(lbl)
                btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                if st == "success":
                    btn.setStyleSheet("""
                        QPushButton {
                            background: rgba(0, 230, 118, 30); color: #00e676;
                            border: 1px solid #00e676; border-radius: 4px; padding: 5px 12px;
                        }
                        QPushButton:hover { background: rgba(0, 230, 118, 70); color: #ffffff; }
                    """)
                elif st in ("warning", "accent"):
                    btn.setStyleSheet("""
                        QPushButton {
                            background: rgba(255, 170, 0, 30); color: #ffaa00;
                            border: 1px solid #ffaa00; border-radius: 4px; padding: 5px 12px;
                        }
                        QPushButton:hover { background: rgba(255, 170, 0, 70); color: #ffffff; }
                    """)
                elif st == "danger":
                    btn.setStyleSheet("""
                        QPushButton {
                            background: rgba(255, 77, 90, 25); color: #ff6b75;
                            border: 1px solid #ff4d5a; border-radius: 4px; padding: 5px 12px;
                        }
                        QPushButton:hover { background: rgba(255, 77, 90, 60); color: #ffffff; }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background: rgba(0, 240, 255, 25); color: #00f0ff;
                            border: 1px solid #00f0ff; border-radius: 4px; padding: 5px 12px;
                        }
                        QPushButton:hover { background: rgba(0, 240, 255, 60); color: #ffffff; }
                    """)
                act_id = act.get("id", "")
                pld = act.get("payload", {})
                if on_close:
                    btn.clicked.connect(on_close)
                btn_row.addWidget(btn)
            btn_row.addStretch()
            lay.addLayout(btn_row)

text = "Vejo que está monitorando os tokens no Antigravity IDE essa hora. Precisa de ajuda com alguma otimização no Mark-LV?"
comp = {
    "type": "ActionDecisionCard",
    "title": "Iniciativa da Evie",
    "data": {
        "description": text,
        "actions": [
            {"id": "proactive_action", "label": "✓ Concordo", "style": "success", "payload": {"choice": "Sim, prossiga."}},
            {"id": "proactive_action", "label": "⏱ Mais tarde", "style": "warning", "payload": {"choice": "Mais tarde."}},
            {"id": "proactive_action", "label": "✕ Dispensar", "style": "danger", "payload": {"choice": "Dispensar."}},
        ]
    }
}

card = ModernActionCard(comp, None, on_close=lambda: print("closed"))
card.setFixedWidth(460)
card.adjustSize()

pm = QPixmap(card.size())
pm.fill(QColor(0, 0, 0, 0))
card.render(pm)
pm.save("scratch/overlay_after.png")
print("Saved scratch/overlay_after.png, size:", card.width(), card.height())
