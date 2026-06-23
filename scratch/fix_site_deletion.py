import os

filepath = r"C:\Users\a0947\Documents\store\apps\site\views.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

found = -1
for i, line in enumerate(lines):
    if 'elif key == "sites":' in line:
        found = i
        break

if found != -1:
    indent = len(lines[found]) - len(lines[found].lstrip())
    spaces = " " * (indent + 4) # Add 4 extra spaces for nested block indentation!
    
    new_lines = [
        spaces + 'c = Site.objects.all().delete()[0]\n',
        spaces + 'from django.conf import settings\n',
        spaces + 'Site.objects.create(id=settings.SITE_ID, domain="raqamiyatapp.com", name="Raqamiyat")\n',
        spaces + 'deleted_counts["مواقع النظام"] = c\n'
    ]
    
    if lines[found].endswith("\r\n"):
        new_lines = [line.replace("\n", "\r\n") for line in new_lines]
        
    lines[found+1:found+5] = new_lines # We replaced lines[found+1:found+3] before, but let's replace the whole block now (4 lines)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("Successfully replaced lines with correct nested indentation!")
else:
    print("Could not find line with Sites key!")
