from pywebpush import webpush, WebPushException
import json
from py_vapid import Vapid

def generate_vapid_keys():
    vapid = Vapid()
    vapid.generate_keys()
    private_key = vapid.private_key.to_string().hex()
    public_key = vapid.public_key.to_string().hex()
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")

if __name__ == "__main__":
    generate_vapid_keys()
