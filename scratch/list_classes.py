import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('ui.py', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    m = re.match(r'^class\s+(\w+)\s*\(([^)]+)\):', line)
    if m:
        cname, base = m.groups()
        print(f"Line {i}: {cname} ({base})")
