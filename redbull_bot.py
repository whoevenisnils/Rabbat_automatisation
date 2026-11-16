import os
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

# Marktguru API (öffentlicher App-Key)
API_URL = "https://api.marktguru.de/api/v1/offers/search"
HEADERS = {
    "x-apikey": "8Kk+pmbf7TgJ9nVj2cXeA5P3b1L0qR4sW6yU8iO0pA=",
    "x-clientkey": "r2D2c3Po00000000000000000000000000000000000=",
    "User-Agent": "Marktguru/5.0 (Android)"
}

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

    params = {
        "as": "web",
        "limit": 50,
        "offset": 0,
        "q": QUERY,
        "zipCode": ZIP_CODE
    }

    try:
        res = requests.get(API_URL, headers=HEADERS, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[-] Fehler beim Abrufen der Marktguru-API: {e}")
        return

    offers = data.get("results", [])
    seen_ids = load_seen()
    new_deals = []

    for offer in offers:
        offer_id = str(offer.get("id"))
        price = offer.get("price")
        product = offer.get("product", {}).get("name", "Red Bull")
        description = offer.get("description", "")
        
        # Prüfen ob "red bull" wirklich im Titel steckt & Preis unter 1 € liegt
        if "red bull" not in product.lower():
            continue
        if price is None or float(price) > MAX_PRICE:
            continue

        # Händlername & Gültigkeit auslesen
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

    # Schöne Discord-Embeds bauen
    embeds = []
    for d in new_deals[:10]:  # Discord erlaubt max. 10 Embeds pro Nachricht
        embeds.append({
            "title": f"🐂 {d['shop']} — {d['price']}",
            "description": f"**{d['product']}**\n{d['desc']}\n📅 **Gültig:** {d['valid']}",
            "color": 0xDB0A40  # Red-Bull-Rot
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
