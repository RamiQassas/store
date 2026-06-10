import os

def fix():
    with open('apps/site/views.py', 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = ""
    for line in content.split('\n'):
        if 'ط' in line or 'ظ' in line or 'ظ…' in line:
            try:
                fixed = line.encode('cp1252').decode('utf-8')
                new_content += fixed + '\n'
            except:
                try:
                    fixed = line.encode('latin-1').decode('utf-8')
                    new_content += fixed + '\n'
                except:
                    new_content += line + '\n'
        else:
            new_content += line + '\n'

    # remove the extra trailing newline added by split
    if new_content.endswith('\n') and not content.endswith('\n'):
        new_content = new_content[:-1]

    with open('apps/site/views.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Fixed file.")

if __name__ == '__main__':
    fix()
