import os

path = r"C:\Users\a0947\Documents\store\err.txt"
if os.path.exists(path):
    try:
        with open(path, "r", encoding="utf-16-le") as f:
            content = f.read()
        print("File read successfully, writing to scratch_err_utf8.txt")
        with open(r"C:\Users\a0947\Documents\store\scratch_err_utf8.txt", "w", encoding="utf-8") as f2:
            f2.write(content)
    except Exception as e:
        print("Error:", e)
else:
    print("File not found")
