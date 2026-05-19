import os
import smtplib
import requests
from email.message import EmailMessage

COLLECTION_URL = "https://nakedandfamousdenimnyc.com/collections/strong-guy/products.json"
PRODUCT_BASE = "https://nakedandfamousdenimnyc.com/products"
SIZE = "31"
RECIPIENT = "matthewli2000@gmail.com"


def find_available():
    resp = requests.get(COLLECTION_URL, params={"limit": 250}, timeout=30)
    resp.raise_for_status()
    products = resp.json()["products"]

    hits = []
    for p in products:
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
        return f"Nothing in size {SIZE} available in the Strong Guy collection today."
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
