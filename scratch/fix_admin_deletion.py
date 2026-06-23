import os

filepath = r"C:\Users\a0947\Documents\store\apps\site\views.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

stores_found = -1
users_found = -1

for i, line in enumerate(lines):
    if 'elif key == "stores":' in line:
        stores_found = i
    elif 'elif key == "users":' in line:
        users_found = i

if stores_found != -1:
    print(f"Found 'stores' on line {stores_found+1}")
    # Replace:
    # c = Store.objects.all().delete()[0]
    # with:
    # User.objects.all().update(store=None)
    # c = Store.objects.all().delete()[0]
    indent = len(lines[stores_found]) - len(lines[stores_found].lstrip())
    spaces = " " * (indent + 4)
    
    line_to_replace = lines[stores_found+2]
    print(f"Replacing stores line: {repr(line_to_replace)}")
    
    new_store_lines = [
        spaces + 'User.objects.all().update(store=None)\n',
        spaces + 'c = Store.objects.all().delete()[0]\n'
    ]
    if line_to_replace.endswith("\r\n"):
        new_store_lines = [line.replace("\n", "\r\n") for line in new_store_lines]
        
    lines[stores_found+2:stores_found+3] = new_store_lines

# Re-evaluate index for users since list length changed by +1
for i, line in enumerate(lines):
    if 'elif key == "users":' in line:
        users_found = i
        break

if users_found != -1:
    print(f"Found 'users' on line {users_found+1}")
    indent = len(lines[users_found]) - len(lines[users_found].lstrip())
    spaces = " " * (indent + 4)
    
    line_to_replace = lines[users_found+1]
    print(f"Replacing users line: {repr(line_to_replace)}")
    
    new_user_line = spaces + 'c = User.objects.exclude(is_superuser=True).exclude(is_staff=True).exclude(role__in=[User.Role.SUPER_ADMIN, User.Role.ADMIN]).exclude(id=request.user.id).delete()[0]\n'
    if line_to_replace.endswith("\r\n"):
        new_user_line = new_user_line.replace("\n", "\r\n")
        
    lines[users_found+1] = new_user_line

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Replacement complete successfully!")
