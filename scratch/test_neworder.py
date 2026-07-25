import requests

headers = {
    "api-token": "test_token_123",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "AlkasrVIPClient/2.0"
}

endpoints_to_test = ["newOrder", "neworder", "order", "orders", "createOrder"]

for ep in endpoints_to_test:
    url = f"https://api.alkasr-vip.com/client/api/{ep}"
    rg = requests.get(url, headers=headers, timeout=5)
    rp = requests.post(url, headers=headers, timeout=5)
    print(f"/{ep}: GET={rg.status_code} POST={rp.status_code}")
    if rg.status_code != 404:
        print(f"  GET response: {rg.text[:200]}")
    if rp.status_code != 404:
        print(f"  POST response: {rp.text[:200]}")
