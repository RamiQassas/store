import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('apps/site/views.py', 'rb') as f:
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

print(f"Fixed {mojibake_count} lines of Mojibake in apps/site/views.py.")
