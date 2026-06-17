import requests, json

token = "2840789b-d1ee-af89-6433-8d1f8a509bf9"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR"

urls = {
    "sin_false+json":   f"{BASE}/736407/es/0700/BIE/2.0/{token}?type=json",
    "sin_false+area00": f"{BASE}/736407/es/00/BIE/2.0/{token}?type=json",
    "false+0700+json":  f"{BASE}/736407/es/0700/false/BIE/2.0/{token}?type=json",
    "area_700":         f"{BASE}/736407/es/700/BIE/2.0/{token}?type=json",
    "dos_param_json":   f"{BASE}/736407/es/0700/0/BIE/2.0/{token}?type=json",
    "tema_false":       f"{BASE}/736407/es/0700/false/true/BIE/2.0/{token}?type=json",
}

for nombre, url in urls.items():
    try:
        r = requests.get(url, timeout=15, headers=headers)
        ct = r.headers.get("Content-Type", "")
        body = r.text[:150]
        print(f"[{nombre}] Status={r.status_code}")
        print(f"  {body!r}")
        print()
    except Exception as e:
        print(f"[{nombre}] ERROR: {e}")
        print()
