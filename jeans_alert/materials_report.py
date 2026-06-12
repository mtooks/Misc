"""Build the full material report = live catalog + discontinued (Wayback) jeans.

Run jeans_alert/discontinued.py first to populate discontinued_raw.json, then
this script merges everything into jeans_alert/materials.md.
"""
import json
import os
from collections import defaultdict

from list_materials import crawl, material_of, norm, example_link, PRODUCT_BASE

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(_HERE, "discontinued_raw.json")


def wayback_url(rec):
    return f"https://web.archive.org/web/{rec['ts']}/{rec['url']}"


def build():
    # --- Active materials: live main-domain jeans ---
    active = defaultdict(list)
    for p in crawl():
        if p.get("product_type") != "Jeans":
            continue
        m = material_of(p["title"])
        if m:
            active[m.casefold()].append(("active", m, p))

    # --- Discontinued materials: recovered from Wayback ---
    discontinued = defaultdict(list)
    with open(CACHE, encoding="utf-8") as f:
        cache = json.load(f)
    for rec in cache.values():
        title = rec.get("title")
        if not title:
            continue
        m = material_of(title)
        if m:
            discontinued[m.casefold()].append(("past", m, rec, title))

    keys = sorted(set(active) | set(discontinued))
    rows = []
    for k in keys:
        acts = active.get(k, [])
        pasts = discontinued.get(k, [])
        display = acts[0][1] if acts else pasts[0][1]
        if acts and pasts:
            status = "Active + past"
        elif acts:
            status = "Active"
        else:
            status = "Discontinued"
        if acts:
            ex = example_link([p for _, _, p in acts])
            link = f"[{norm(ex['title'])}]({PRODUCT_BASE}/{ex['handle']})"
        else:
            _, _, rec, title = pasts[0]
            link = f"[{title}]({wayback_url(rec)}) _(archived)_"
        rows.append((display, len(acts) + len(pasts), status, link))

    n_active = len(active)
    n_past_only = sum(1 for k in discontinued if k not in active)
    lines = [
        "# Naked & Famous — denim & fabric catalog (active + discontinued)",
        "",
        f"_{len(keys)} distinct materials: {n_active} in the live catalog, "
        f"{n_past_only} recovered only from the Wayback Machine archive._",
        "",
        "| Material | # products | Status | Example |",
        "| --- | --- | --- | --- |",
    ]
    for display, n, status, link in rows:
        lines.append(f"| {display} | {n} | {status} | {link} |")
    return "\n".join(lines) + "\n", len(keys), n_active, n_past_only


if __name__ == "__main__":
    md, total, n_active, n_past = build()
    with open(os.path.join(_HERE, "materials.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Wrote jeans_alert/materials.md: {total} materials "
          f"({n_active} active, {n_past} discontinued-only)")
