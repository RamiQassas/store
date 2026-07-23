import sys

with open('apps/site/views.py', 'r', encoding='utf-8') as f:
    text = f.read()

def fix_line(line):
    # Check if line contains mojibake indicators
    if any(c in line for c in ['Ø', 'Ù', 'â', 'Øª', 'Ø§', 'ÙŠ']):
        try:
            return line.encode('cp1252').decode('utf-8')
        except Exception:
            try:
                return line.encode('latin1').decode('utf-8')
            except Exception:
                pass
    return line

sample = "âš¡ ØªÙ… Ø¨Ø¯Ø¡ ØªØ­Ø¯ÙŠØ« Ø§Ù„Ø±ØµÙŠØ¯ ÙˆØ§Ù„Ø¨ÙŠØ§Ù†Ø§Øª Ù ÙŠ Ø§Ù„Ø®Ù„Ù ÙŠØ© Ø¨Ù†Ø¬Ø§Ø­."
print("Sample original:", sample)
print("Sample fixed:   ", fix_line(sample))
