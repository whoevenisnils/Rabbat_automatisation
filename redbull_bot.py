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
MAX_PRICE_PER_CAN = 1.00  # Max. Preis PRO DOSE (funktioniert auch für 4er-Packs etc.!)
SEEN_FILE = "seen_deals.json"

# Optionaler Filter für Größen & Packs:
# Lass die Liste leer `[]` für ALLE Größen, oder trage ein, was du willst, z. B.:
# ALLOWED_SIZES = ["0,25", "0.25", "250", "4er", "4 x", "4x"]
ALLOWED_SIZES = []

API_URL = "https://api.marktguru.de/api/v1/offers/search"

def get_marktguru_keys():
    """Liest den aktuell gültigen API-Key dynamisch aus der Marktguru-Webseite."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    res = requests.get("https://www.marktguru.de/", headers=headers, timeout=15)
    res.raise_for_status()
    html = res.text

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

def parse_pack_and_size(text):
    """Erkennt Packungsgröße (z. B. 4er-Pack, 24er-Tray) und Dosengröße (z. B. 0,25l, 0,33l)."""
    t = text.lower()
    
    # Pack-Anzahl erkennen (z. B. "4 x 0,25", "4x0.25", "4er pack", "4er-pack", "6er", "12er", "24er")
    pack_count = 1
    pack_match = re.search(r'(\d+)\s*(?:er[\s-]*pack|er[\s-]*tray|er\b|x\s*0[.,]\d+|x\s*\d+\s*ml)', t)
    if pack_match:
        count = int(pack_match.group(1))
        if count in (2, 4, 6, 8, 10, 12, 24):
            pack_count = count

    # Dosengröße erkennen (z. B. 0,25 l / 250 ml / 0,33 l / 355 ml / 473 ml)
    size_label = "Einzeldose" if pack_count == 1 else f"{pack_count}er-Pack"
    vol_match = re.search(r'(0[.,](?:25|33|355|473)\s*l|(?:250|330|355|473)\s*ml)', t)
    if vol_match:
        vol = vol_match.group(1).replace(" ", "")
        size_label = f"{pack_count}x {vol}" if pack_count > 1 else f"1x {vol}"

    return pack_count, size_label

def detect_app_deal(text):
    """Prüft, ob das Angebot an eine Supermarkt-App (Lidl Plus, Kaufland Card/Xtra, etc.) gebunden ist."""
    t = text.lower()
    apps = []
    if "lidl plus" in t:
        apps.append("Lidl Plus")
    if "kaufland card" in t or "xtra" in t:
        apps.append("Kaufland Card / Xtra")
    if "rewe bonus" in t or "rewe app" in t:
        apps.append("REWE Bonus / App")
    if "penny app" in t:
        apps.append("PENNY App")
    if "edeka app" in t or "genuss+" in t:
        apps.append("EDEKA App")
    if "netto app" in t or "netto+" in t:
        apps.append("Netto App")
    if not apps and ("mit app" in t or "app-preis" in t or "app preis" in t or "nur in der app" in t):
        apps.append("Supermarkt-App")
    return ", ".join(apps)

def check_redbull():
    if not WEBHOOK_URL:
        print("[-] Fehler: DISCORD_WEBHOOK Secret fehlt!")
        return

    try:
        api_key, client_key = get_marktguru_keys()
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
        "limit": 60,
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
    print(f"[*] {len(offers)} Treffer insgesamt in {ZIP_CODE} gefunden:")

    seen_ids = load_seen()
    new_deals = []

    for offer in offers:
        offer_id = str(offer.get("id"))
        raw_price = offer.get("price")
        product = (offer.get("product") or {}).get("name") or offer.get("title") or "Red Bull"
        description = offer.get("description") or ""
        
        # Zusätzliche Textfelder von Marktguru für App-Hinweise & Größen auslesen
        price_info = str(offer.get("priceInformation") or "")
        unit_info = str(offer.get("unit") or "")
        full_text = f"{product} {description} {price_info} {unit_info}"

        advertisers = offer.get("advertisers", [])
        shop = advertisers[0].get("name", "Unbekannter Markt") if advertisers else "Unbekannter Markt"

        if raw_price is None:
            continue

        try:
            total_price = float(str(raw_price).replace(",", "."))
        except ValueError:
            continue

        pack_count, size_label = parse_pack_and_size(full_text)
        price_per_can = total_price / pack_count
        app_badge = detect_app_deal(full_text)

        print(f"   -> {shop} | {product} | {size_label} | Gesamt: {total_price:.2f}€ ({price_per_can:.2f}€/Dose) | App: {app_badge or 'Nein'}")

        # Optionaler Größenfilter
        if ALLOWED_SIZES:
            if not any(s.lower() in full_text.lower() for s in ALLOWED_SIZES):
                continue

        # Preisgrenze pro Dose prüfen
        if price_per_can > MAX_PRICE_PER_CAN:
            continue

        validity = (offer.get("validityDates") or [{}])[0]
        valid_from = format_date(validity.get("from"))
        valid_to = format_date(validity.get("to"))

        deal_key = f"{offer_id}_{total_price}"
        if deal_key not in seen_ids:
            seen_ids.add(deal_key)
            
            price_str = f"{total_price:.2f}".replace(".", ",") + " €"
            if pack_count > 1:
                can_str = f"{price_per_can:.2f}".replace(".", ",") + " €/Dose"
                price_display = f"{price_str} ({can_str})"
            else:
                price_display = price_str

            new_deals.append({
                "shop": shop,
                "product": product,
                "size": size_label,
                "price": price_display,
                "app": app_badge,
                "desc": description,
                "valid": f"{valid_from} – {valid_to}"
            })

    if not new_deals:
        print("[*] Keine neuen passenden Red-Bull-Deals gefunden.")
        return

    embeds = []
    for d in new_deals[:10]:
        desc_lines = [
            f"**{d['product']}**",
            f"📦 **Größe / Pack:** {d['size']}",
        ]
        if d["app"]:
            desc_lines.append(f"📱 **App-Rabatt:** {d['app']}")
        if d["desc"]:
            desc_lines.append(f"ℹ️ {d['desc']}")
        desc_lines.append(f"📅 **Gültig:** {d['valid']}")

        embeds.append({
            "title": f"🐂 {d['shop']} — {d['price']}",
            "description": "\n".join(desc_lines),
            "color": 0x004C97 if d["app"] else 0xDB0A40  # Blau bei App-Deal, Rot bei normalem Angebot
        })

    payload = {
        "content": f"🚨 <@{DISCORD_USER_ID}> **Red Bull Alarm in {ZIP_CODE}!** ({len(new_deals)} neuer Deal)",
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
