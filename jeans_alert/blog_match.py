"""Match each fabric to a Naked & Famous blog post (its release announcement)
and recompute the season/year release table.

Date priority per fabric:
  1. earliest blog post whose title/handle names the fabric  (announcement date)
  2. else earliest live Shopify `created_at` across its fits  (store-add date)
  3. else no date                                             (discontinued, unseen)

Blog dates fix the `created_at`-reset problem (bulk re-uploads) AND give dates to
discontinued fabrics that have no live product at all.
"""
import json
import re
from collections import Counter, defaultdict

from build_catalog import collect, normkey
from list_materials import crawl, material_of

BLOG_CACHE = "jeans_alert/blog_cache.json"
OVERRIDES = "jeans_alert/blog_overrides.json"     # {fabric_normkey: blog_handle}
EXTRA = "jeans_alert/blog_extra_fabrics.json"     # [{handle, name}] blog-only fabrics
BLOG = "https://nakedandfamousdenim.com/blogs/naked-and-famous-denim"
SEASON = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring",
          5: "Spring", 6: "Summer", 7: "Summer", 8: "Summer", 9: "Fall",
          10: "Fall", 11: "Fall"}
ORDER = ["Winter", "Spring", "Summer", "Fall"]

# Generic words that carry no fabric identity — ignored when matching titles.
STOP = {"the", "a", "an", "and", "x", "of", "with", "in", "to", "for", "is",
        "selvedge", "denim", "jeans", "jean", "naked", "famous", "oz", "stretch",
        "fit", "fits", "guy", "guys", "new", "release", "released", "back",
        "stock", "limited", "edition", "collection", "collab", "collaboration",
        "weird", "easy", "super", "true", "strong", "skinny", "stacked",
        "groovy", "max", "arrow", "bestie", "womens", "women", "high", "meet",
        "introducing", "our", "now", "available"}


def toks(s):
    return [w for w in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if w]


def distinctive(s):
    return [w for w in toks(s) if w not in STOP and len(w) > 1]


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return default


def load_blog():
    out = []
    for handle, v in load_json(BLOG_CACHE, {}).items():
        if not v.get("date"):
            continue
        key = set(toks(handle)) | set(toks(v.get("title", "")))
        out.append({"handle": handle, "date": v["date"], "key": key,
                    "title": v.get("title", ""), "text": v.get("text", ""),
                    "images": v.get("images", [])})
    return out


def load_overrides():
    return load_json(OVERRIDES, {})


def load_extras():
    return load_json(EXTRA, [])


def season_label(date):
    """'2025-07-07' -> 'Summer 2025'; None -> None."""
    if not date:
        return None
    return f"{SEASON[int(date[5:7])]} {date[:4]}"


def resolve_blog_map(rows, posts):
    """{fabric_normkey: blog_handle}: token auto-matches, then hand overrides win."""
    m = {}
    for r in rows:
        bp = best_post(r["name"], posts)
        if bp:
            m[normkey(r["name"])] = bp["handle"]
    m.update(load_overrides())
    return m


def best_post(name, posts):
    """Blog post that names this fabric: every distinctive fabric token must be
    present in the post's title/handle (>=2 tokens, or the lone token). Among
    matches, prefer one that contains the fabric's distinctive tokens as a
    contiguous phrase (so "Blue Comfort" picks the Blue-Comfort post, not the
    earliest post that merely mentions "blue" and "comfort"), then the earliest."""
    fab = distinctive(name)
    if not fab:
        return None
    phrase = " ".join(fab)
    hits = []
    for p in posts:
        matched = [t for t in fab if t in p["key"]]
        if not ((len(matched) == len(fab) and len(matched) >= 2)
                or (len(fab) == 1 and matched)):
            continue
        hay = p["handle"].replace("-", " ") + " " + p.get("title", "").lower()
        hits.append((0 if phrase in hay else 1, p["date"], p))
    if not hits:
        return None
    return min(hits, key=lambda h: (h[0], h[1]))[2]   # phrase-match first, then earliest


def created_at_by_material():
    by = defaultdict(list)
    for p in crawl():
        if p.get("product_type") != "Jeans":
            continue
        m = material_of(p["title"])
        if m:
            by[normkey(m)].append(p["created_at"][:10])
    return {k: min(v) for k, v in by.items()}


def table(dates_by_fabric, label):
    grid = Counter()
    for d in dates_by_fabric.values():
        if not d:
            continue
        y, mo = int(d[:4]), int(d[5:7])
        grid[(y, SEASON[mo])] += 1
    years = sorted({y for y, _ in grid})
    print(f"\n=== {label} ===")
    hdr = "Year   " + "".join(f"{s:>8}" for s in ORDER) + f"{'Total':>8}"
    print(hdr); print("-" * len(hdr))
    col = Counter()
    for y in years:
        row = [grid[(y, s)] for s in ORDER]
        for s, v in zip(ORDER, row):
            col[s] += v
        print(f"{y:<7}" + "".join(f"{v:>8}" for v in row) + f"{sum(row):>8}")
    print("-" * len(hdr))
    print(f"{'Total':<7}" + "".join(f"{col[s]:>8}" for s in ORDER)
          + f"{sum(col.values()):>8}")


def main():
    posts = load_blog()
    print(f"blog posts with dates: {len(posts)}")
    rows = collect()                          # 254-fabric universe
    cat = created_at_by_material()

    before = {}   # created_at-only (what we had)
    after = {}    # blog-preferred
    n_blog = n_new = n_corrected = 0
    examples_new = []
    for r in rows:
        nk = normkey(r["name"])
        ca = cat.get(nk)                      # may be None (discontinued)
        before[r["name"]] = ca
        bp = best_post(r["name"], posts)
        if bp:
            n_blog += 1
            after[r["name"]] = bp["date"]
            if not ca:
                n_new += 1
                if len(examples_new) < 12:
                    examples_new.append((bp["date"], r["name"]))
            elif bp["date"][:7] != ca[:7]:
                n_corrected += 1
        else:
            after[r["name"]] = ca

    have_before = sum(1 for v in before.values() if v)
    have_after = sum(1 for v in after.values() if v)
    print(f"fabrics: {len(rows)}")
    print(f"had a date before (created_at):   {have_before}")
    print(f"matched to a blog post:           {n_blog}")
    print(f"  -> NEW dates (had none before): {n_new}")
    print(f"  -> corrected (diff month):      {n_corrected}")
    print(f"have a date now (blog or ca):      {have_after}  (+{have_after - have_before})")
    print("\nsample NEW (previously undated) fabric -> blog date:")
    for d, n in sorted(examples_new):
        print(f"  {d}  {n}")

    table(before, "BEFORE  (created_at only)")
    table(after, "AFTER   (blog-preferred + created_at fallback)")


if __name__ == "__main__":
    main()
