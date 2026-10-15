import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('ui.py', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if re.search(r'btn_close|close_btn|proactive', line, re.I):
            print(f'{i}: {line.strip()[:90]}')
