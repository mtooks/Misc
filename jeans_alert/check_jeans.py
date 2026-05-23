import os
import smtplib
import time
import requests
from email.message import EmailMessage

CATALOG_URL = "https://nakedandfamousdenimnyc.com/products.json"
PRODUCT_BASE = "https://nakedandfamousdenimnyc.com/products"
FIT = "strong guy"
SIZE = "31"
RECIPIENT = "matthewli2000@gmail.com"
MAX_PAGES = 10
PAGE_DELAY = 1.5
MAX_RETRIES = 5


def fetch_page(page):
    for attempt in range(MAX_RETRIES):
        resp = requests.get(CATALOG_URL, params={"limit": 250, "page": page}, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("products", [])
        if resp.status_code in (429, 503):
            wait = int(resp.headers.get("Retry-After", 2 ** attempt * 5))
            time.sleep(min(wait, 60))
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Failed to fetch page {page} after {MAX_RETRIES} retries")


def iter_catalog():
    for page in range(1, MAX_PAGES + 1):
        products = fetch_page(page)
        if not products:
            return
        yield from products
        time.sleep(PAGE_DELAY)


def find_available():
    hits = []
    for p in iter_catalog():
        if FIT not in p["title"].lower():
            continue
        for v in p["variants"]:
            if v.get("option1") == SIZE and v.get("available"):
                hits.append({
                    "title": p["title"],
                    "price": v["price"],
                    "url": f"{PRODUCT_BASE}/{p['handle']}?variant={v['id']}",
                })
    return hits


def build_body(hits):
    if not hits:
        return f"Nothing in size {SIZE} available in the Strong Guy fit today."
    lines = [f"{len(hits)} pair(s) available in size {SIZE}:\n"]
    for h in hits:
        lines.append(f"{h['title']} - ${h['price']}\n{h['url']}\n")
    return "\n".join(lines)


def send_email(hits):
    msg = EmailMessage()
    msg["Subject"] = f"N&F Strong Guy size {SIZE}: {len(hits)} available"
    msg["From"] = RECIPIENT
    msg["To"] = RECIPIENT
    msg.set_content(build_body(hits))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(RECIPIENT, os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)


if __name__ == "__main__":
    send_email(find_available())
