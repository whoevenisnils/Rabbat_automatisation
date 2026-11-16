import os
import re
import json
import requests
from datetime import datetime

# --- KONFIGURATION ---
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DISCORD_USER_ID = "699686432293519532"

ZIP_CODE = "58239"
QUERY = "Red Bull"
MAX_PRICE = 0.99  # Alles unter 1,00 €
SEEN_FILE = "seen_deals.json"

API_URL = "https://api.marktguru.de/api/v1/offers/search"

def get_marktguru_keys():
    """Liest den aktuell gültigen API-Key dynamisch aus der Marktguru-Webseite."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    res = requests.get("https://www.marktguru.de/", headers=headers, timeout=15)
    res.raise_for_status()
    html = res.text

    # Marktguru bettet config/apiKey direkt im HTML/JS ein
    api_match = re.search(r'"apiKey"\s*:\s*"([^"]+)"', html)
    client_match = re.search(r'"clientKey"\s*:\s*"([^"]+)"', html)

    if not api_match:
        raise RuntimeError("Konnte keinen aktuellen apiKey auf marktguru.de finden.")

    api_key = api_match.group(1)
    client_key = client_match.group(1) if client_match else "r2D2c3Po00000000000000000000000000000000000="
    return api_key, client_key

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_seen(seen_ids):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, indent=2)

def format_date(iso_str):
    if not iso_str:
        return "?"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.")
    except Exception:
        return iso_str[:10]

def check_redbull():
    if not WEBHOOK_URL:
        print("[-] Fehler: DISCORD_WEBHOOK Secret fehlt!")
        return

    try:
        api_key, client_key = get_marktguru_keys()
        print("[+] Aktuellen Marktguru API-Key erfolgreich geladen.")
    except Exception as e:
        print(f"[-] Fehler beim Laden des API-Keys: {e}")
        return

    headers = {
        "x-apikey": api_key,
        "x-clientkey": client_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://www.marktguru.de",
        "Referer": "https://www.marktguru.de/"
    }

    params = {
        "as": "web",
        "limit": 50,
        "offset": 0,
        "q": QUERY,
        "zipCode": ZIP_CODE
    }

    try:
        res = requests.get(API_URL, headers=headers, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[-] Fehler beim Abrufen der Marktguru-API: {e}")
        return

    offers = data.get("results", [])
    print(f"[*] {len(offers)} Red-Bull-Einträge insgesamt in {ZIP_CODE} gefunden.")
    seen_ids = load_seen()
    new_deals = []

    for offer in offers:
        offer_id = str(offer.get("id"))
        price = offer.get("price")
        product = offer.get("product", {}).get("name", "Red Bull")
        description = offer.get("description", "")

        if "red bull" not in product.lower():
            continue
        if price is None or float(price) > MAX_PRICE:
            continue

        advertisers = offer.get("advertisers", [])
        shop = advertisers[0].get("name", "Unbekannter Markt") if advertisers else "Unbekannter Markt"

        validity = offer.get("validityDates", [{}])[0]
        valid_from = format_date(validity.get("from"))
        valid_to = format_date(validity.get("to"))

        deal_key = f"{offer_id}_{price}"
        if deal_key not in seen_ids:
            seen_ids.add(deal_key)
            new_deals.append({
                "shop": shop,
                "product": product,
                "price": f"{float(price):.2f}".replace(".", ",") + " €",
                "desc": description,
                "valid": f"{valid_from} – {valid_to}"
            })

    if not new_deals:
        print("[*] Keine neuen Red-Bull-Deals unter 1,00 € gefunden.")
        return

    embeds = []
    for d in new_deals[:10]:
        embeds.append({
            "title": f"🐂 {d['shop']} — {d['price']}",
            "description": f"**{d['product']}**\n{d['desc']}\n📅 **Gültig:** {d['valid']}",
            "color": 0xDB0A40
        })

    payload = {
        "content": f"🚨 <@{DISCORD_USER_ID}> **Red Bull Alarm in {ZIP_CODE}!** ({len(new_deals)} neuer Deal unter 1 €)",
        "embeds": embeds
    }

    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code in (200, 204):
        print(f"[+] {len(new_deals)} Deal(s) erfolgreich an Discord gesendet!")
        save_seen(seen_ids)
    else:
        print(f"[-] Discord-Fehler: {r.status_code} – {r.text}")

if __name__ == "__main__":
    check_redbull()
