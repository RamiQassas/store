import os

file_path = r"C:\Users\a0947\Documents\store\services\provider\alkasr\mapper.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
in_try = False

for i, line in enumerate(lines):
    if i == 58: # line 59 which is '                try:\n'
        in_try = True
        new_lines.append(line)
    elif i == 176: # line 177 which is '            except Exception as e:\n'
        in_try = False
        new_lines.append(line)
    elif in_try:
        if line.strip() == "":
            new_lines.append("\n")
        else:
            new_lines.append("    " + line)
    else:
        new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
