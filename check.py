#!/usr/bin/env python3
"""
PS5-Pro-Wächter
Prüft MediaMarkt, Saturn und PlayStation Direct und schickt eine Push-
Nachricht (ntfy, optional zusätzlich E-Mail), sobald die PS5 Pro bestellbar
ist und höchstens MAX_PRICE kostet. Benachrichtigt wird nur beim Wechsel
"nicht verfügbar" -> "verfügbar", damit du nicht alle 10 Minuten gepingt wirst.
"""

import json
import os
import re
from pathlib import Path

from curl_cffi import requests

MAX_PRICE = float(os.environ.get("MAX_PRICE") or "899.99")
NTFY_SERVER = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_EMAIL = os.environ.get("NTFY_EMAIL", "").strip()
TEST_NOTIFY = os.environ.get("TEST_NOTIFY", "").lower() == "true"
STATE_FILE = Path(os.environ.get("STATE_FILE") or "state.json")
BLOCK_ALERT_AFTER = 6  # so viele fehlgeschlagene Abrufe in Folge -> eine Info-Push

SHOPS = [
    {"name": "MediaMarkt", "kind": "mms",
     "url": "https://www.mediamarkt.de/de/product/_sony-playstationr5-pro-2-tb-konsole-3018022.html"},
    {"name": "Saturn", "kind": "mms",
     "url": "https://www.saturn.de/de/product/_sony-playstationr5-pro-2-tb-konsole-3018022.html"},
    {"name": "PlayStation Direct", "kind": "sony",
     "url": "https://www.playstation.com/de-de/ps5/ps5-pro/buy-now/"},
]

HEADERS = {"Accept-Language": "de-DE,de;q=0.9,en;q=0.5"}

BUYABLE = {"instock": "auf Lager", "limitedavailability": "begrenzt verfügbar",
           "onlineonly": "online verfügbar", "preorder": "vorbestellbar"}
BLOCK_MARKERS = ["access denied", "pardon our interruption", "request unsuccessful",
                 "are you a robot", "challenge-platform", "px-captcha"]
MMS_OOS_TEXT = ["online ausverkauft", "dieser artikel ist aktuell nicht verfügbar",
                "leider nicht mehr verfügbar", "derzeit nicht lieferbar"]
SONY_OOS_TEXT = ["derzeit nicht vorrätig", "nicht zum kauf erhältlich", "ausverkauft"]


def fetch(url):
    # impersonate="chrome" imitiert den TLS-Fingerabdruck eines echten Browsers,
    # was gegen einfache Bot-Erkennung deutlich besser funktioniert als requests.
    r = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=30)
    return r.status_code, r.text


def parse_price(value):
    if value is None:
        return None
    s = str(value).strip().replace("\u20ac", "").replace(" ", "")
    if "," in s and "." in s:          # 1.249,95
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                      # 899,99
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def iter_jsonld(html):
    pattern = r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for m in re.finditer(pattern, html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                yield node
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))


def find_offer(html):
    """Liefert (availability, price) aus den strukturierten Produktdaten der Seite."""
    for node in iter_jsonld(html):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(t in ("Offer", "AggregateOffer") for t in types) and node.get("availability"):
            avail = str(node["availability"]).rsplit("/", 1)[-1].lower()
            return avail, parse_price(node.get("price", node.get("lowPrice")))
    # Fallback: Verfügbarkeit irgendwo im eingebetteten JSON
    m = re.search(r'"availability"\s*:\s*"(?:https?://schema\.org/)?(\w+)"', html)
    if m:
        return m.group(1).lower(), None
    return None


def check_mms(url):
    code, html = fetch(url)
    if code != 200:
        return {"status": "blocked", "detail": f"HTTP {code}"}
    low = html.lower()
    offer = find_offer(html)
    if offer:
        avail, price = offer
        if avail not in BUYABLE:
            return {"status": "unavailable", "detail": f"{avail}, {price}"}
        if price is not None and price > MAX_PRICE + 0.01:
            return {"status": "too_expensive", "detail": f"{avail}, {price:.2f} €"}
        return {"status": "available", "label": BUYABLE[avail], "price": price}
    if any(m in low for m in BLOCK_MARKERS):
        return {"status": "blocked", "detail": "Bot-Schutz-Seite"}
    if any(m in low for m in MMS_OOS_TEXT):
        return {"status": "unavailable", "detail": "Text: ausverkauft"}
    return {"status": "unknown", "detail": "keine Produktdaten gefunden"}


def check_sony(url):
    code, html = fetch(url)
    if code != 200:
        return {"status": "blocked", "detail": f"HTTP {code}"}
    low = html.lower()
    if "ps5" not in low or "pro" not in low:
        return {"status": "unknown", "detail": "unerwartete Seite"}
    if any(m in low for m in SONY_OOS_TEXT):
        return {"status": "unavailable", "detail": "nicht vorrätig"}
    # Sony verkauft selbst immer zur UVP, daher keine Preisprüfung nötig.
    return {"status": "available", "label": "bestellbar", "price": None}


def notify(title, message, priority=4, tags=None, click=None, email=False):
    if not NTFY_TOPIC:
        print(f"[ohne NTFY_TOPIC, nur Log] {title}: {message}")
        return
    payload = {"topic": NTFY_TOPIC, "title": title, "message": message, "priority": priority}
    if tags:
        payload["tags"] = tags
    if click:
        payload["click"] = click
    if email and NTFY_EMAIL:
        payload["email"] = NTFY_EMAIL
    r = requests.post(NTFY_SERVER, json=payload, timeout=20)
    if r.status_code >= 300:
        print(f"ntfy-Fehler {r.status_code}: {r.text[:200]}")


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main():
    state = load_state()
    before = json.dumps(state, sort_keys=True)

    if TEST_NOTIFY:
        notify("PS5-Pro-Wächter: Test",
               "Wenn du das liest, kommen die Benachrichtigungen an.",
               priority=4, tags=["white_check_mark"], email=True)

    for shop in SHOPS:
        name, url = shop["name"], shop["url"]
        try:
            result = check_mms(url) if shop["kind"] == "mms" else check_sony(url)
        except Exception as e:  # Netzwerkfehler, Timeouts usw.
            result = {"status": "blocked", "detail": f"{type(e).__name__}: {e}"}

        status = result["status"]
        print(f"{name:<20} {status:<14} {result.get('detail', '')}")
        s = state.setdefault(name, {"status": None, "failed_runs": 0})

        if status == "available" and s.get("status") != "available":
            price = result.get("price")
            price_txt = f"{price:.2f} €".replace(".", ",") if price else "Preis bitte prüfen"
            notify(f"PS5 Pro bei {name}!",
                   f"{result['label']} – {price_txt}\n{url}",
                   priority=5, tags=["video_game", "rotating_light"], click=url, email=True)

        if status in ("blocked", "unknown"):
            if s.get("failed_runs", 0) < BLOCK_ALERT_AFTER:
                s["failed_runs"] = s.get("failed_runs", 0) + 1
                if s["failed_runs"] == BLOCK_ALERT_AFTER:
                    notify(f"Wächter: {name} nicht prüfbar",
                           f"{name} lässt sich seit {BLOCK_ALERT_AFTER} Durchläufen nicht abrufen "
                           f"({result.get('detail', '')}). Für diesen Shop bist du gerade nicht abgedeckt.",
                           priority=2, tags=["warning"])
        else:
            if s.get("failed_runs", 0) >= BLOCK_ALERT_AFTER:
                notify(f"Wächter: {name} wieder prüfbar", "Läuft wieder normal.",
                       priority=2, tags=["white_check_mark"])
            s["failed_runs"] = 0
            s["status"] = status  # bei Blockaden bleibt der letzte echte Status stehen

    after = json.dumps(state, sort_keys=True)
    if after != before:
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
