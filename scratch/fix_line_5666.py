with open('apps/site/views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if 'ğŸš€' in line or 'Ø¨Ø¯Ø£Øª Ø¹Ù…Ù„ÙŠØ© Ø§Ù„Ù…Ø²Ø§Ù…Ù†Ø©' in line:
        new_lines.append('            messages.success(request, "🚀 بدأت عملية المزامنة بنجاح في الخلفية! يتم الآن سحب واستيراد كافة المنتجات وتحديث الكتالوج تلقائياً دون أي إبطاء.")\n')
    else:
        new_lines.append(line)

with open('apps/site/views.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Line 5666 replaced successfully!")
