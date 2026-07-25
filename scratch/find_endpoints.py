import requests

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "AlkasrVIPClient/2.0"
}

endpoints = [
    "profile", "products", "check", "newOrder", "new_order", "order", "orders",
    "createOrder", "create_order", "addOrder", "add_order"
]

base = "https://api.alkasr-vip.com/client/api/"

for ep in endpoints:
    url = base + ep
    r_g = requests.get(url, headers=headers, timeout=5)
    r_p = requests.post(url, headers=headers, timeout=5)
    print(f"Endpoint /{ep}: GET={r_g.status_code} POST={r_p.status_code}")
    if r_g.status_code != 404:
        print(f"   GET Snippet: {r_g.text[:150]}")
    if r_p.status_code != 404:
        print(f"   POST Snippet: {r_p.text[:150]}")
