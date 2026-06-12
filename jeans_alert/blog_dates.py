"""Crawl the Naked & Famous Shopify blog and cache each post's date + text.

The blog announces fabric/collab releases, so a post's publish date is a much
better release-date proxy than Shopify `created_at` (which resets on re-uploads)
and is the ONLY date signal we have for discontinued fabrics. Output cache:
jeans_alert/blog_cache.json  ->  {handle: {title, date, text, images}}

Run modes:
  python jeans_alert/blog_dates.py            # full crawl/resume of every post
  python jeans_alert/blog_dates.py --extras   # refetch only blog-only fabric
                                              # posts (to populate hero images)
"""
import json
import os
import re
import sys
import time

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
BLOG = "https://nakedandfamousdenim.com/blogs/naked-and-famous-denim"
CACHE = os.path.join(_HERE, "blog_cache.json")
EXTRA = os.path.join(_HERE, "blog_extra_fabrics.json")
PAGES = 20          # listing pages to sweep (stops early when empty)
REQ_DELAY = 1.2     # polite gap between requests (sequential)
# A real browser UA + modest rate keeps the storefront from serving the
# "Verifying your connection..." interstitial that blocks default requests.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36"}
S = requests.Session()
S.headers.update(HEADERS)


def get(url, **kw):
    """GET with 429/challenge-aware exponential backoff."""
    for attempt in range(7):
        r = S.get(url, timeout=30, **kw)
        if r.status_code == 200 and "Verifying your connection" not in r.text:
            return r.text
        time.sleep(min(60, 5 * 2 ** attempt))   # 5,10,20,40,60,60,60
    return r.text


def list_handles():
    handles = {}
    for pg in range(1, PAGES + 1):
        h = get(BLOG, params={"page": pg})
        found = re.findall(r"/blogs/naked-and-famous-denim/([a-z0-9][a-z0-9-]+)", h)
        new = {x for x in found if x not in handles}
        if not new:
            break
        for x in new:
            handles[x] = None
        time.sleep(REQ_DELAY)
    return list(handles)


def first_image(h):
    """First content image (Shopify CDN) on the page, for blog-only fabric cards.
    Reads src/data-src before tags are stripped; skips logos/icons."""
    for src in re.findall(r'(?:data-src|src)="(//[^"]+|https?://[^"]+)"', h):
        if "cdn.shopify" not in src and "shopify.com/s/files" not in src:
            continue
        low = src.lower()
        if any(b in low for b in ("logo", "icon", "sprite", ".svg")):
            continue
        if not re.search(r"\.(jpe?g|png|webp)", low):
            continue
        url = "https:" + src if src.startswith("//") else src
        return url.split("?")[0] + "?width=700"
    return None


def fetch_article(handle):
    h = get(f"{BLOG}/{handle}")
    date = re.search(r'"datePublished"\s*:\s*"([^"]+)"', h)
    title = re.search(r"<title>(.*?)</title>", h, re.S)
    img = first_image(h)
    # crude body: strip tags from the article body region if findable, else whole page
    body = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body)
    return {
        "title": (title.group(1).strip() if title else handle),
        "date": (date.group(1)[:10] if date else None),
        "text": body[:6000],
        "images": [img] if img else [],
    }


def save(cache):
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), indent=0)


def main():
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except FileNotFoundError:
        cache = {}
    listed = list_handles()
    # Universe = freshly listed handles + any already in cache (survive a blocked listing).
    handles = list(dict.fromkeys(listed + list(cache)))
    print(f"listed {len(listed)}, total known {len(handles)}", flush=True)
    todo = [h for h in handles if not cache.get(h, {}).get("date")]
    print(f"fetching {len(todo)} without a cached date (sequential)", flush=True)
    for i, h in enumerate(todo, 1):
        try:
            cache[h] = fetch_article(h)
        except requests.RequestException:
            cache.setdefault(h, {"title": h, "date": None, "text": "", "images": []})
        if i % 25 == 0:
            dated = sum(1 for v in cache.values() if v["date"])
            print(f"  {i}/{len(todo)}  ({dated} dated so far)", flush=True)
            save(cache)        # periodic checkpoint so the run is resumable
        time.sleep(REQ_DELAY)
    save(cache)
    dated = sum(1 for v in cache.values() if v["date"])
    print(f"wrote {CACHE}: {len(cache)} posts, {dated} with a date")


def refetch_extras():
    """Refetch only the blog-only fabric posts to (re)populate hero images,
    even when they already have a cached date."""
    cache = json.load(open(CACHE, encoding="utf-8"))
    handles = [e["handle"] for e in json.load(open(EXTRA, encoding="utf-8"))]
    todo = [h for h in handles if not cache.get(h, {}).get("images")]
    print(f"refetching {len(todo)}/{len(handles)} extra-fabric posts for images", flush=True)
    for i, h in enumerate(todo, 1):
        try:
            cache[h] = fetch_article(h)
        except requests.RequestException:
            pass
        if i % 10 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
            save(cache)
        time.sleep(REQ_DELAY)
    save(cache)
    got = sum(1 for h in handles if cache.get(h, {}).get("images"))
    print(f"done: {got}/{len(handles)} extra posts now have a hero image")


if __name__ == "__main__":
    if "--extras" in sys.argv:
        refetch_extras()
    else:
        main()
