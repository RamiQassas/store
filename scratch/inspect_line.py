with open('apps/site/views.py', 'rb') as f:
    lines = f.readlines()

line5683 = lines[5682]
print("Raw bytes of line 5683:")
print(line5683)

text5683 = line5683.decode('utf-8', errors='replace')
print("Decoded utf-8:")
print(text5683)
