"""Recover discontinued Naked & Famous jeans from the Wayback Machine.

products.json and sitemap.xml only contain currently-published products, so
anything discontinued (e.g. the Rick & Morty "Pickle Rick" selvedge) is gone.
The Wayback Machine's CDX index lists every product URL ever archived; we diff
that against the live catalog, then read each archived page's <og:title> to get
the real product title and parse its material the same way as the live list.
"""
import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from list_materials import material_of, norm

DOMAINS = ["nakedandfamousdenim.com", "nakedandfamousdenimnyc.com"]
# Handle tokens that mark a jeans fit (men's "* Guy" handled separately via "guy").
WOMENS_JEANS = ["high-skinny", "true-girl", "super-girl", "maudie", "bestie"]
# Title-side fits used to confirm a fetched product really is a pair of jeans.
JEANS_FITS = {
    "weird guy", "super guy", "easy guy", "true guy", "strong guy", "skinny guy",
    "groovy guy", "stacked guy", "high skinny", "true girl", "super girl",
    "maudie", "bestie", "max",
}
_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(_HERE, "discontinued_raw.json")
WORKERS = 4


def live_handles():
    handles = set()
    for dom in DOMAINS:
        for page in range(1, 40):
            b = requests.get(f"https://{dom}/products.json",
                             params={"limit": 250, "page": page}, timeout=30
                             ).json().get("products", [])
            if not b:
                break
            for p in b:
                handles.add(p["handle"].lower())
            time.sleep(0.3)
    return handles


def clean_handle(url):
    hd = url.split("/products/")[1].split("?")[0].split("#")[0].rstrip("/").lower()
    for suf in (".js", ".json", ".oembed", ".xml", ".html", ".htm"):
        if hd.endswith(suf):
            hd = hd[: -len(suf)]
    return hd


def archived_jeans():
    """Return {(domain, handle): (clean_url, latest_timestamp)} for discontinued jeans."""
    live = live_handles()
    found = {}
    for dom in DOMAINS:
        rows = None
        for attempt in range(6):
            try:
                resp = requests.get("https://web.archive.org/cdx/search/cdx",
                                    params={"url": f"{dom}/products/*", "output": "json",
                                            "collapse": "urlkey",
                                            "fl": "original,timestamp,statuscode"},
                                    timeout=120)
                if resp.status_code == 200:
                    rows = resp.json()[1:]
                    break
            except requests.RequestException:
                pass
            time.sleep(5 * (attempt + 1))
        if rows is None:
            raise RuntimeError(f"Wayback CDX unavailable for {dom} (throttled?)")
        for original, ts, status in rows:
            if status != "200":
                continue
            hd = clean_handle(original)
            if hd in live:
                continue
            if "guy" not in hd and not any(f in f"-{hd}-" for f in WOMENS_JEANS):
                continue
            key = (dom, hd)
            if key not in found or ts > found[key][1]:
                found[key] = (original.split("?")[0], ts)
    return found


def fetch_title(dom, url, ts):
    snap = f"https://web.archive.org/web/{ts}id_/{url}"
    for attempt in range(5):
        try:
            r = requests.get(snap, timeout=60)
            if r.status_code in (429, 503, 502, 504):  # Wayback throttling
                time.sleep(2 ** attempt)
                continue
            r.encoding = "utf-8"  # Wayback omits charset; pages are UTF-8
            m = re.search(r'<meta property=["\']og:title["\'] content=["\']([^"\']+)', r.text)
            if not m:
                m = re.search(r"<title>([^<]+)</title>", r.text)
            if not m:
                return None
            title = html.unescape(m.group(1))
            title = re.split(r"\s*[|–-]\s*Naked", title)[0]  # drop "| Naked & Famous..."
            return norm(title)
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None


def title_is_jeans(title):
    segs = [norm(s) for s in title.split(" - ") if norm(s)]
    if not segs:
        return False
    fit = segs[1] if re.sub(r"[^a-z]", "", segs[0].lower()) == "womens" and len(segs) > 1 else segs[0]
    fit = fit.lower()
    return fit in JEANS_FITS or "guy" in fit


def main():
    targets = archived_jeans()
    print(f"discontinued jeans handles to fetch: {len(targets)}", flush=True)

    try:
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except FileNotFoundError:
        cache = {}

    # Re-fetch anything missing OR previously failed (title is None).
    todo = {k: v for k, v in targets.items()
            if not cache.get(f"{k[0]}|{k[1]}", {}).get("title")}
    print(f"resolved & cached: {len(targets) - len(todo)}; (re)fetching: {len(todo)}", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_title, dom, url, ts): (dom, hd)
                for (dom, hd), (url, ts) in todo.items()}
        for fut in as_completed(futs):
            dom, hd = futs[fut]
            title = fut.result()
            cache[f"{dom}|{hd}"] = {"domain": dom, "handle": hd, "title": title,
                                    "url": targets[(dom, hd)][0], "ts": targets[(dom, hd)][1]}
            done += 1
            if done % 25 == 0:
                print(f"  fetched {done}/{len(todo)}", flush=True)
                with open(CACHE, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=0)

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=0)
    got = sum(1 for v in cache.values() if v.get("title"))
    print(f"done. titles resolved: {got}/{len(cache)}", flush=True)


if __name__ == "__main__":
    main()
