import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('ui.py', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if re.search(r'QPushButton\([\'\"][xX\u2715\u2716\u00d7]', line):
        # find what class this line is in
        class_name = "Unknown"
        for j in range(i-1, -1, -1):
            if lines[j].startswith("class "):
                class_name = lines[j].strip()
                break
        print(f"Line {i} in {class_name}: {line.strip()[:100]}")
