import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('ui.py', encoding='utf-8') as f:
    text = f.read()

# Find all occurrences of border-radius in stylesheets
matches = re.findall(r'(\w+)\s*\{[^}]*border-radius:[^}]*\}', text)
print("Widgets with border-radius stylesheets:")
for m in set(matches):
    print(f" - {m}")

# Find all occurrences of "✕" or "X" or "CLOSE"
print("\nClose buttons in ui.py:")
for i, line in enumerate(text.splitlines(), 1):
    if any(k in line for k in ['"✕"', "'✕'", '"X"', "'X'", "QPushButton"]):
        if any(w in line for w in ["close", "hide", "x_btn", "btn_close", "dismiss"]):
            print(f"Line {i}: {line.strip()[:90]}")
