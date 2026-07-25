import py_compile
import sys
import traceback

try:
    py_compile.compile(r'C:\Users\a0947\Documents\store\services\provider\alkasr\mapper.py', doraise=True)
    print('OK')
except Exception as e:
    traceback.print_exc()
    sys.exit(1)
