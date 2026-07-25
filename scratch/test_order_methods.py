import requests

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "AlkasrVIPClient/2.0"
}

url_new = "https://api.alkasr-vip.com/client/api/newOrder"
r_new = requests.post(url_new, headers=headers, timeout=10)
print(f"POST /newOrder Status: {r_new.status_code}, Body: {r_new.text[:300]}")

url_check = "https://api.alkasr-vip.com/client/api/check"
r_check = requests.post(url_check, headers=headers, timeout=10)
print(f"POST /check Status: {r_check.status_code}, Body: {r_check.text[:300]}")
