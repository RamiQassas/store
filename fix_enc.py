import os

def fix():
    with open('apps/site/views.py', 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = ""
    # find lines with mojibake
    for line in content.split('\n'):
        if 'ط' in line or 'ظ' in line:
            try:
                # The text was written as utf-8, but powershell read it as windows-1252 and then saved it as utf-8.
                line = line.encode('windows-1252').decode('utf-8')
            except:
                pass
        new_content += line + '\n'

    with open('apps/site/views.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == '__main__':
    fix()
