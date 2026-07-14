"""
test_scrapingdog.py — Diagnóstico de endpoints de Scrapingdog.
Ejecutar desde la carpeta del proyecto:
    python scripts/test_scrapingdog.py
"""
import requests
import json

API_KEY = "6a4d2666e306cff132b69acc"
BASE    = "https://api.scrapingdog.com"


def _test(nombre, url, params):
    print(f"\n{'-'*60}")
    print(f"TEST: {nombre}")
    print(f"URL : {url}")
    print(f"PARAMS: { {k: v for k,v in params.items() if k != 'api_key'} }")
    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"STATUS: {r.status_code}")
        ct = r.headers.get("Content-Type", "?")
        print(f"Content-Type: {ct}")
        txt = r.text.strip()
        if not txt:
            print("BODY: (vacío)")
            return
        # Intentar parse JSON
        try:
            data = r.json()
            if isinstance(data, list):
                print(f"TIPO: lista con {len(data)} elementos")
                if data:
                    print(f"KEYS[0]: {list(data[0].keys())[:10] if isinstance(data[0], dict) else type(data[0])}")
            elif isinstance(data, dict):
                print(f"TIPO: dict, KEYS: {list(data.keys())[:15]}")
                # Buscar listas anidadas
                for k, v in data.items():
                    if isinstance(v, list):
                        print(f"  [{k}] → lista con {len(v)} elementos")
            else:
                print(f"TIPO: {type(data).__name__}, VALOR: {str(data)[:200]}")
        except Exception:
            print(f"BODY (no JSON): {txt[:300]}")
    except Exception as e:
        print(f"ERROR de conexión: {e}")


print("=" * 60)
print("DIAGNÓSTICO SCRAPINGDOG — TYASA BI")
print("=" * 60)

# ── LinkedIn ──────────────────────────────────────────────────────────────────
_test("LinkedIn type=company (Ternium)", f"{BASE}/linkedin",
      {"api_key": API_KEY, "type": "company", "linkId": "ternium"})

_test("LinkedIn type=company_posts (Ternium)", f"{BASE}/linkedin",
      {"api_key": API_KEY, "type": "company_posts", "linkId": "ternium"})

_test("LinkedIn type=company_updates (Deacero)", f"{BASE}/linkedin",
      {"api_key": API_KEY, "type": "company_updates", "linkId": "deacero"})

# ── Facebook ──────────────────────────────────────────────────────────────────
_test("Facebook /facebook/profile (Ternium.mx)", f"{BASE}/facebook/profile",
      {"api_key": API_KEY, "username": "Ternium.mx"})

_test("Facebook /facebook/posts (Ternium.mx)", f"{BASE}/facebook/posts",
      {"api_key": API_KEY, "username": "Ternium.mx"})

_test("Facebook /facebook (Ternium.mx)", f"{BASE}/facebook",
      {"api_key": API_KEY, "username": "Ternium.mx"})

# ── Instagram ─────────────────────────────────────────────────────────────────
_test("Instagram /instagram/posts username= (aceroternium)", f"{BASE}/instagram/posts",
      {"api_key": API_KEY, "username": "aceroternium"})

_test("Instagram /instagram username= (aceroternium)", f"{BASE}/instagram",
      {"api_key": API_KEY, "username": "aceroternium"})

# ── Twitter/X ─────────────────────────────────────────────────────────────────
_test("X/Twitter /x/profile profileId=Ternium", f"{BASE}/x/profile",
      {"api_key": API_KEY, "profileId": "Ternium"})

_test("X/Twitter /x/profile username=Ternium", f"{BASE}/x/profile",
      {"api_key": API_KEY, "username": "Ternium"})

print("\n" + "=" * 60)
print("FIN DEL DIAGNÓSTICO")
print("=" * 60)
