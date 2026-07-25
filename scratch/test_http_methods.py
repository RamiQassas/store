import requests

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "AlkasrVIPClient/2.0"
}

url_prod = "https://api.alkasr-vip.com/client/api/products"
print("Testing GET /products...")
r_get = requests.get(url_prod, headers=headers, timeout=10)
print(f"GET /products Status: {r_get.status_code}, Length: {len(r_get.text)}")
print(f"GET /products Body snippet: {r_get.text[:300]}")

print("\nTesting POST /products...")
r_post = requests.post(url_prod, headers=headers, timeout=10)
print(f"POST /products Status: {r_post.status_code}, Length: {len(r_post.text)}")

url_prof = "https://api.alkasr-vip.com/client/api/profile"
print("\nTesting GET /profile...")
r_prof_get = requests.get(url_prof, headers=headers, timeout=10)
print(f"GET /profile Status: {r_prof_get.status_code}, Body snippet: {r_prof_get.text[:300]}")

print("\nTesting POST /profile...")
r_prof_post = requests.post(url_prof, headers=headers, timeout=10)
print(f"POST /profile Status: {r_prof_post.status_code}, Body snippet: {r_prof_post.text[:300]}")
