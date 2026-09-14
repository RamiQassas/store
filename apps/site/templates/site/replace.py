import re

file_path = r'c:\Users\a0947\Documents\store\apps\site\templates\site\catalog.html'
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # CSS variable and hex replacements
    replacements = {
        'var(--cyan, #2dd4bf)': 'var(--gold, #d4a853)',
        'var(--cyan)': 'var(--gold)',
        '#2dd4bf': '#d4a853',
        'rgba(45,212,191,': 'rgba(212,168,83,',
        'rgba(34,211,238,': 'rgba(212,168,83,',
        '#06b6d4': '#d4a853',
        '#6366f1': '#7c5cbf',
        'rgba(99,102,241,': 'rgba(124,92,191,',
        '#a5b4fc': '#b8a5e8',
        '#ea580c': '#e85d75',
        'text-cyan': 'text-gold'
    }

    for old, new in replacements.items():
        content = content.replace(old, new)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Done!')
except Exception as e:
    print(f'Error: {e}')
