"""Consolidated Naked & Famous fabric catalog from every source we found:

  1. Live Shopify catalog  (products.json)        -> currently buyable, shop link
  2. Squarespace fabric pages (sitemap.xml)        -> full fabric archive, incl.
                                                      discontinued/limited runs
  3. Wayback Machine (discontinued_raw.json cache) -> archived shop links

Squarespace is the master list (it has a showcase page per fabric, active or
not). Each fabric is fuzzy-matched to a live product for a shop link; if it
isn't sold anymore it links to its Squarespace page (and an archived product
page when the Wayback crawl has one).
"""
import json
import os
import re

import requests

from list_materials import crawl, material_of, norm, example_link, PRODUCT_BASE

SQ = "https://nakedandfamousdenim.squarespace.com"
_HERE = os.path.dirname(os.path.abspath(__file__))
WAYBACK_CACHE = os.path.join(_HERE, "discontinued_raw.json")

# --- Squarespace slug filtering ----------------------------------------------
DROP_SUFFIX = ("-lifestyle", "-flat", "-macro", "-macros", "-faded", "-teaser",
               "-lookbook", "-process", "-applying", "-posters", "-poster",
               "-gallery")
DROP_PREFIX = ("aloha-shirt", "chore-coat", "denim-jacket", "easy-shirt",
               "pocket-tee", "kimono-shirt", "work-shirt", "over-shirt",
               "band-collar", "twin-pleat", "womens-overalls", "upcycled",
               "watchcap", "mug", "knife", "customized-leather", "higonokami",
               "making-of", "stackable", "milk-glass", "the-gambler", "hijet",
               "vivid-vans", "spring-summer", "rick-and-morty",
               "rick-morty-announcement", "15th-anniversary-post",
               "store-locator", "new-gallery", "gallery")
DROP_EXACT = {"nice-guy", "raver-guy", "rainbow", "36-long-inseam",
              "higonokami-knives", "vulgar-selvedge-3"}
# Any slug containing one of these tokens is a garment/merch/photo page, not a fabric.
DROP_TOKENS = {"shirt", "tee", "jacket", "coat", "overall", "overalls", "short",
               "shorts", "cap", "hat", "watchcap", "mug", "mugs", "knife", "knives",
               "hoodie", "sweat", "sock", "socks", "scarf", "belt", "wallet",
               "bandana", "beanie", "romper", "dress", "skirt", "poster", "posters",
               "gallery", "lookbook", "sticker", "pin", "tote", "macro", "macros",
               "lifestyle", "teaser", "announcement", "process"}
# Fit prefixes to strip so "strong-guy-dirty-fade-stretch-selvedge" -> the fabric.
FIT_PREFIX = ("weird-guy-", "super-guy-", "easy-guy-", "true-guy-", "strong-guy-",
              "skinny-guy-", "groovy-guy-", "stacked-guy-", "womens-")


def squarespace_fabrics():
    xml = requests.get(f"{SQ}/sitemap.xml", timeout=60).text
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    slugs = []
    for url in locs:
        if not url.startswith(SQ):
            continue
        path = url[len(SQ):]
        if path.count("/") != 1 or not path[1:]:
            continue
        slug = path[1:]
        if slug in DROP_EXACT or slug.split("/")[0] in {"en", "fr"}:
            continue
        if any(slug.endswith(s) for s in DROP_SUFFIX):
            continue
        if any(slug.startswith(p) for p in DROP_PREFIX):
            continue
        if DROP_TOKENS & set(slug.split("-")):
            continue
        slugs.append(slug)
    out = {}
    for slug in sorted(set(slugs)):
        fabric = slug
        for fp in FIT_PREFIX:
            if fabric.startswith(fp):
                fabric = fabric[len(fp):]
                break
        title = " ".join(w.capitalize() for w in fabric.split("-"))
        out[title] = slug  # de-dups fit variants that reduce to same fabric
    return out


def normkey(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def fuzzy_find(name, live_by_key):
    """Find a live material whose name contains / is contained by `name`."""
    nk = normkey(name)
    if nk in live_by_key:
        return live_by_key[nk]
    if len(nk) < 6:
        return None
    for lk, rec in live_by_key.items():
        if len(lk) >= 6 and (nk in lk or lk in nk):
            return rec
    return None


def shopify_images(product, limit=6):
    out = []
    for im in (product.get("images") or [])[:limit]:
        src = im["src"]
        out.append(src + ("&" if "?" in src else "?") + "width=700")
    return out


def weight_oz(text):
    """First plausible denim weight in oz found in the text (e.g. '14.5oz')."""
    for m in re.finditer(r"(\d{1,2}(?:\.\d+)?)\s?oz", text or "", re.I):
        val = float(m.group(1))
        if 4 <= val <= 40:
            return val
    return None


def strip_html(text):
    """Plain text from an HTML fragment (for description-based tagging)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def collect():
    """Merge all sources into structured rows (used by markdown + HTML report)."""
    live_by_key = {}
    by_material = {}
    for p in crawl():
        if p.get("product_type") != "Jeans":
            continue
        m = material_of(p["title"])
        if m:
            by_material.setdefault(m, []).append(p)
    for m, prods in by_material.items():
        # Prefer an in-stock fit for the example/shop link so an "available" card
        # always links to a fit you can actually buy (not a sold-out one); fall
        # back to any fit when nothing is in stock.
        in_stock_prods = [p for p in prods
                          if any(v.get("available") for v in p.get("variants", []))]
        ex = example_link(in_stock_prods or prods)
        live_by_key[normkey(m)] = {
            "name": m, "url": f"{PRODUCT_BASE}/{ex['handle']}", "n": len(prods),
            "in_stock": bool(in_stock_prods),
            # earliest fit = closest thing Shopify has to this fabric's release;
            # desc (shop description) is the best source for oz + fiber.
            "created_at": min((p.get("created_at") or "")[:10] for p in prods),
            "desc": strip_html(ex.get("body_html")),
            "images": shopify_images(ex), "weight_oz": weight_oz(ex.get("body_html"))}

    archived_by_key = {}
    if os.path.exists(WAYBACK_CACHE):
        for rec in json.load(open(WAYBACK_CACHE, encoding="utf-8")).values():
            if not rec.get("title"):
                continue
            m = material_of(rec["title"])
            if m:
                archived_by_key.setdefault(normkey(m), rec)

    sq = squarespace_fabrics()
    rows = {}
    used_live = set()
    for title, slug in sq.items():
        live = fuzzy_find(title, live_by_key)
        if live:
            used_live.add(normkey(live["name"]))
            rows[normkey(live["name"])] = {
                "name": live["name"], "status": "active", "in_stock": live["in_stock"],
                "images": live["images"],
                "weight_oz": live["weight_oz"], "shop_url": live["url"],
                "shop_fits": live["n"], "archived_url": None,
                "showcase_url": f"{SQ}/{slug}", "slug": slug,
                "blog_url": None, "release_date": None,
                "desc": live["desc"], "_created_at": live["created_at"]}
        else:
            arc = archived_by_key.get(normkey(title))
            rows[normkey(title)] = {
                "name": title, "status": "discontinued", "in_stock": False,
                "images": [],
                "weight_oz": None, "shop_url": None, "shop_fits": None,
                "archived_url": (f"https://web.archive.org/web/{arc['ts']}/{arc['url']}"
                                 if arc else None),
                "showcase_url": f"{SQ}/{slug}", "slug": slug,
                "blog_url": None, "release_date": None,
                "desc": "", "_created_at": None}

    for lk, rec in live_by_key.items():
        if lk not in used_live and lk not in rows:
            rows[lk] = {"name": rec["name"], "status": "active", "in_stock": rec["in_stock"],
                        "images": rec["images"],
                        "weight_oz": rec["weight_oz"], "shop_url": rec["url"],
                        "shop_fits": rec["n"], "archived_url": None,
                        "showcase_url": None, "slug": None,
                        "blog_url": None, "release_date": None,
                        "desc": rec["desc"], "_created_at": rec["created_at"]}

    enrich_with_blog(rows)
    return sorted(rows.values(), key=lambda r: r["name"].lower())


def enrich_with_blog(rows):
    """Attach blog_url + release_date, fold blog text into desc, and append the
    blog-only 'missed' fabrics. Imported lazily to avoid a circular import
    (blog_match imports this module). Mutates `rows` (a {normkey: row} dict)."""
    from blog_match import load_blog, resolve_blog_map, load_extras, BLOG

    posts = load_blog()
    by_handle = {p["handle"]: p for p in posts}
    blog_map = resolve_blog_map(rows.values(), posts)   # {normkey: handle}

    for nk, r in rows.items():
        ca = r.pop("_created_at", None)
        handle = blog_map.get(nk)
        bp = by_handle.get(handle) if handle else None
        if handle:
            r["blog_url"] = f"{BLOG}/{handle}"
        # release date: blog announcement first, else earliest Shopify created_at
        r["release_date"] = (bp["date"] if bp else None) or ca
        # NB: blog `text` is the whole page (incl. related-post links naming other
        # fabrics), so it is NOT folded into desc — tagging uses the clean shop
        # description only.

    # "missed" fabrics that only the blog knows about (deduped by normkey)
    for ex in load_extras():
        nk = normkey(ex["name"])
        if nk in rows:
            continue
        bp = by_handle.get(ex["handle"])
        rows[nk] = {
            "name": ex["name"], "status": "discontinued", "in_stock": False,
            "images": (bp.get("images") if bp else None) or [],
            "weight_oz": None, "shop_url": None, "shop_fits": None,
            "archived_url": None, "showcase_url": None, "slug": None,
            "blog_url": f"{BLOG}/{ex['handle']}",
            "release_date": bp["date"] if bp else None,
            "desc": "",   # no clean per-fabric description available
        }


def build_markdown(rows):
    n_active = sum(1 for r in rows if r["status"] == "active")
    n_disc = len(rows) - n_active

    def cell(r):
        if r["status"] == "active":
            return f"[shop ({r['shop_fits']} fits)]({r['shop_url']})"
        return f"[archived]({r['archived_url']})" if r["archived_url"] else "—"

    lines = [
        "# Naked & Famous — complete fabric catalog",
        "",
        f"_{len(rows)} distinct fabrics — {n_active} currently sold, "
        f"{n_disc} discontinued/limited (recovered from the fabric-page archive "
        f"& Wayback Machine)._",
        "",
        "| Fabric | Status | Buy / Archived | Showcase |",
        "| --- | --- | --- | --- |",
    ]
    for r in rows:
        status = "Active" if r["status"] == "active" else "Discontinued / limited"
        showcase = f"[page]({r['showcase_url']})" if r["showcase_url"] else "—"
        lines.append(f"| {r['name']} | {status} | {cell(r)} | {showcase} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    rows = collect()
    with open(os.path.join(_HERE, "materials.md"), "w", encoding="utf-8") as f:
        f.write(build_markdown(rows))
    n_active = sum(1 for r in rows if r["status"] == "active")
    print(f"Wrote jeans_alert/materials.md: {len(rows)} fabrics "
          f"({n_active} active, {len(rows) - n_active} discontinued/limited)")
