import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

file_path = os.path.abspath('apps/site/views.py')

with open(file_path, 'rb') as f:
    raw_content = f.read()

lines = raw_content.decode('utf-8', errors='replace').splitlines(keepends=True)

def cp1252_to_bytes(text_segment):
    res = bytearray()
    for ch in text_segment:
        try:
            b = ch.encode('cp1252')
            res.extend(b)
        except UnicodeEncodeError:
            try:
                b = ch.encode('latin1')
                res.extend(b)
            except UnicodeEncodeError:
                res.extend(ch.encode('utf-8'))
    return bytes(res)

fixed_lines = []
mojibake_count = 0

for line in lines:
    if any(m in line for m in ['Ø', 'Ù', 'âš¡', 'ØªÙ…', 'Ø§Ù„', 'ÙŠ']):
        b = cp1252_to_bytes(line)
        try:
            dec = b.decode('utf-8')
            fixed_lines.append(dec)
            mojibake_count += 1
            continue
        except Exception:
            pass
    fixed_lines.append(line)

new_content = "".join(fixed_lines)

with open(file_path, 'w', encoding='utf-8', newline='') as f:
    f.write(new_content)

print(f"Successfully repaired {mojibake_count} Mojibake lines in {file_path}")
