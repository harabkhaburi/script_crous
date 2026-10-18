import html
import json
import os

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------
# Réglages (les seuls endroits à modifier si besoin)
# ---------------------------------------------------------------
URL = (
    "https://trouverunlogement.lescrous.fr/tools/47/search"
    "?bounds=6.134292_48.7092349_6.2126188_48.666906"
    "&locationName=Nancy+%2854000%29"
)

# Si une annonce contient ce mot, elle est marquée avec une étoile.
# Mettre "" pour désactiver.
WATCH_WORD = "monbois"

# True  = alerter pour TOUTES les annonces
# False = alerter seulement pour celles qui contiennent WATCH_WORD
ALERT_ON_EVERYTHING = True

SEEN_FILE = "seen.json"
BASE = "https://trouverunlogement.lescrous.fr"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Secrets Telegram manquants (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
    except requests.RequestException as e:
        print(f"Erreur reseau Telegram: {e}")
        return False
    if r.status_code != 200:
        print(f"Erreur Telegram {r.status_code}: {r.text}")
        return False
    return True


def parse(page_html):
    """Retourne un dict {id_annonce: infos} pour toutes les annonces de la page."""
    soup = BeautifulSoup(page_html, "html.parser")
    cards = soup.find_all(class_=lambda c: c and "fr-card" in c) or soup.find_all("li")
    found = {}
    for card in cards:
        link = card.find("a", href=lambda h: h and "/accommodations/" in h)
        if not link:
            continue
        href = link["href"]
        full_link = href if href.startswith("http") else BASE + href
        title = link.get_text(" ", strip=True) or "Logement CROUS"

        price = None
        node = card.find(string=lambda t: t and "€" in t)
        if node:
            price = " ".join(str(node).split())

        size = None
        for p in card.find_all("p"):
            if "m²" in p.get_text():
                size = " ".join(p.get_text().split())
                break

        found[full_link] = {
            "title": title,
            "price": price,
            "size": size,
            "link": full_link,
            "text": card.get_text(" ", strip=True),
        }
    return found


def is_watched(item):
    return bool(WATCH_WORD) and WATCH_WORD.lower() in item["text"].lower()


def format_item(item):
    star = "⭐ " if is_watched(item) else ""
    lines = [f"{star}<b>{html.escape(item['title'])}</b>"]
    details = []
    if item["price"]:
        details.append(f"💰 {html.escape(item['price'])}")
    if item["size"]:
        details.append(f"📏 {html.escape(item['size'])}")
    if details:
        lines.append(" | ".join(details))
    lines.append(f"🔗 <a href='{item['link']}'>Voir le logement</a>")
    return "\n".join(lines)


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def save_seen(ids):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=1)


def main():
    if os.environ.get("TEST_MESSAGE", "").lower() == "true":
        ok = send_telegram("✅ Test : le bot CROUS fonctionne.")
        print("Message de test envoye." if ok else "Echec du message de test.")
        return

    try:
        response = requests.get(URL, headers=HEADERS, timeout=20)
        response.encoding = "utf-8"
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Erreur reseau: {e}")
        return  # on ne touche pas a seen.json en cas d'erreur

    current = parse(response.text)
    if not ALERT_ON_EVERYTHING:
        current = {k: v for k, v in current.items() if is_watched(v)}

    previous = load_seen()
    new_ids = [k for k in current if k not in previous]
    print(f"{len(current)} annonce(s) visibles, {len(new_ids)} nouvelle(s).")

    if new_ids:
        # les annonces marquees d'une etoile en premier
        new_items = sorted(
            (current[k] for k in new_ids), key=lambda it: not is_watched(it)
        )
        all_sent = True
        for i in range(0, len(new_items), 8):
            batch = new_items[i : i + 8]
            head = f"🚨 <b>{len(new_items)} nouveau(x) logement(s) à Nancy !</b>\n\n"
            if not send_telegram(head + "\n\n".join(format_item(it) for it in batch)):
                all_sent = False
        if not all_sent:
            return  # reessayer au prochain passage

    save_seen(set(current))


if __name__ == "__main__":
    main()
