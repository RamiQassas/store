import os

filepath = r"C:\Users\a0947\Documents\store\apps\site\views.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

ordered_cleanup_keys_line = -1
invoices_handler_line = -1

for i, line in enumerate(lines):
    if '"invoices",' in line:
        ordered_cleanup_keys_line = i
    if 'elif key == "invoices":' in line:
        invoices_handler_line = i

if ordered_cleanup_keys_line != -1:
    print(f"Found 'invoices' key on line {ordered_cleanup_keys_line+1}")
    # Insert "coupons", after "invoices",
    indent = len(lines[ordered_cleanup_keys_line]) - len(lines[ordered_cleanup_keys_line].lstrip())
    spaces = " " * indent
    new_key_line = spaces + '"coupons",\n'
    if lines[ordered_cleanup_keys_line].endswith("\r\n"):
        new_key_line = new_key_line.replace("\n", "\r\n")
    lines.insert(ordered_cleanup_keys_line + 1, new_key_line)

# Re-evaluate invoices_handler_line in case list length changed
for i, line in enumerate(lines):
    if 'elif key == "invoices":' in line:
        invoices_handler_line = i
        break

if invoices_handler_line != -1:
    print(f"Found invoices handler on line {invoices_handler_line+1}")
    indent = len(lines[invoices_handler_line]) - len(lines[invoices_handler_line].lstrip())
    spaces = " " * indent
    
    new_handler_lines = [
        spaces + 'elif key == "coupons":\n',
        spaces + '    from apps.orders.models import Coupon\n',
        spaces + '    c = Coupon.objects.all().delete()[0]\n',
        spaces + '    deleted_counts["الكوبونات"] = c\n'
    ]
    
    # Handle CRLF
    if lines[invoices_handler_line].endswith("\r\n"):
        new_handler_lines = [line.replace("\n", "\r\n") for line in new_handler_lines]
        
    lines[invoices_handler_line:invoices_handler_line] = new_handler_lines # Insert before invoices handler

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Added coupons to database cleanup targets successfully!")
