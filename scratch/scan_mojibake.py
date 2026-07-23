import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

mojibake_files = []

for root, dirs, files in os.walk('.'):
    if any(p in root for p in ['.git', 'node_modules', 'venv', '.agents', '__pycache__', 'scratch', 'brain']):
        continue
    for file in files:
        if file.endswith(('.py', '.html', '.js', '.json', '.md', '.txt')):
            path = os.path.join(root, file)
            try:
                with open(path, 'rb') as f:
                    content = f.read().decode('utf-8', errors='ignore')
                if any(m in content for m in ['ØªÙ…', 'Ø§Ù„Ø', 'Ø¨Ø¯Ø¡']):
                    mojibake_files.append(path)
            except Exception:
                pass

print("Files containing Mojibake:")
for p in mojibake_files:
    print(p)
