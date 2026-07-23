import sys
sys.stdout.reconfigure(encoding='utf-8')

sample = "ğŸš€ Ø¨Ø¯Ø£Øª Ø¹Ù…Ù„ÙŠØ© Ø§Ù„Ù…Ø²Ø§Ù…Ù†Ø© Ø¨Ù†Ø¬Ø§Ø­ Ù ÙŠ Ø§Ù„Ø®Ù„Ù ÙŠØ©! ÙŠØªÙ… Ø§Ù„Ø¢Ù† Ø³Ø­Ø¨ ÙˆØ§Ø³ØªÙŠØ±Ø§Ø¯ ÙƒØ§Ù Ø© Ø§Ù„Ù…Ù†ØªØ¬Ø§Øª ÙˆØªØ­Ø¯ÙŠØ« Ø§Ù„ÙƒØªØ§Ù„ÙˆØ¬ ØªÙ„Ù‚Ø§Ø¦ÙŠØ§Ù‹ Ø¯ÙˆÙ† Ø£ÙŠ Ø¥Ø¨Ø·Ø§Ø¡."

def cp1252_to_bytes_advanced(text_segment):
    res = bytearray()
    for ch in text_segment:
        if ch == 'ğ':
            res.append(0xf0)
            continue
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

b = cp1252_to_bytes_advanced(sample)
print("Decoded sample:")
print(b.decode('utf-8'))
