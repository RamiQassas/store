with open('apps/site/views.py', 'rb') as f:
    lines = f.readlines()
with open('apps/site/views.py', 'wb') as f:
    for line in lines[:1383]:
        f.write(line)
