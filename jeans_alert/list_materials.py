"""Crawl the Naked & Famous catalog and list every distinct denim/material,
with a link to an example pair of jeans.

Naked & Famous names each fabric and reuses that name across many fits, so a
material is the product title with the fit and color stripped off. Title shape:

    [Women's -] <Fit> - <Material> [- <Color>] [- <Inseam note>]

e.g. "Women's - High Skinny - Black Cobra Stretch Selvedge"
     "True Guy - Blood Brothers Selvedge - Indigo x Black"
     "Easy Guy - Solid Black Selvedge - 36\" Long Inseam"
"""
import html
import os
import re
import time
from collections import defaultdict

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
HOST = "nakedandfamousdenim.com"
CATALOG_URL = f"https://{HOST}/products.json"
PRODUCT_BASE = f"https://{HOST}/products"
MAX_PAGES = 30
PAGE_DELAY = 0.4

# Trailing color tokens that are appended to a fabric name with " - ".
# Only stripped when they are a separate trailing segment, so a one-word
# fabric is never accidentally erased.
COLORS = {
    "indigo", "black", "brown", "bleach blue", "off white", "ecru",
    "mid indigo", "pale indigo", "pale blue", "antique blue", "indigo x black",
    "olive drab", "desert sunset", "grey", "gray", "white", "blue",
}

# Fits we prefer to link as the "example pair", most iconic first.
PREFERRED_FITS = ["Weird Guy", "Easy Guy", "Super Guy", "True Guy", "Strong Guy"]


def crawl():
    products = []
    for page in range(1, MAX_PAGES + 1):
        resp = requests.get(CATALOG_URL, params={"limit": 250, "page": page}, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        time.sleep(PAGE_DELAY)
    return products


def norm(s):
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def material_of(title):
    segs = [norm(s) for s in title.split(" - ") if norm(s)]
    if len(segs) < 2:
        return None
    # Drop an optional "Women's" prefix, then the fit (always the next segment).
    if re.sub(r"[^a-z]", "", segs[0].lower()) == "womens":
        segs = segs[1:]
    segs = segs[1:]  # drop the fit
    if not segs:
        return None
    # Strip a trailing inseam/length note, then a trailing color.
    if len(segs) > 1 and "inseam" in segs[-1].lower():
        segs = segs[:-1]
    if len(segs) > 1 and segs[-1].lower() in COLORS:
        segs = segs[:-1]
    return " - ".join(segs)


def example_link(products):
    """Pick the most iconic fit as the example, else the first product."""
    for fit in PREFERRED_FITS:
        for p in products:
            if p["title"].startswith(fit + " "):
                return p
    return products[0]


def build():
    jeans = [p for p in crawl() if p.get("product_type") == "Jeans"]
    materials = defaultdict(list)
    for p in jeans:
        m = material_of(p["title"])
        if m:
            materials[m].append(p)

    lines = [
        "# Naked & Famous — denim & fabric catalog",
        "",
        f"_{len(materials)} distinct materials across {len(jeans)} jeans "
        f"(scraped from {HOST}/products.json)._",
        "",
        "| Material | # fits | Example pair |",
        "| --- | --- | --- |",
    ]
    for m in sorted(materials, key=str.lower):
        ex = example_link(materials[m])
        url = f"{PRODUCT_BASE}/{ex['handle']}"
        lines.append(f"| {m} | {len(materials[m])} | [{norm(ex['title'])}]({url}) |")
    return "\n".join(lines) + "\n", len(materials), len(jeans)


if __name__ == "__main__":
    md, n_mat, n_jeans = build()
    with open(os.path.join(_HERE, "materials.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Wrote jeans_alert/materials.md: {n_mat} materials, {n_jeans} jeans")
