import sys
import traceback

try:
    import apps.site.views
    print("Success")
except BaseException as e:
    print("Error:")
    traceback.print_exc()
