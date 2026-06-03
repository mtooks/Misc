"""Fast preview of discontinued materials derived from the URL/handle tree
(the Wayback CDX index) WITHOUT fetching each archived page.

Shopify handles look like  brand-fit-material-color, e.g.
  naked-famou-denim-easy-guy-pickle-rick-selvedge -> "Pickle Rick Selvedge"
This is approximate (handles are lowercased and carry occasional typos);
discontinued.py later refines names from the real archived <og:title>.
"""
import re
from collections import defaultdict

from discontinued import archived_jeans

BRAND_PREFIXES = [
    "naked-famous-denim-", "naked-famou-denim-", "naked-and-famous-denim-",
    "naked-famous-", "naked-famou-", "naked-and-famous-", "nf-",
]
# Leading fit tokens to drop (multi-word fits joined by '-').
FIT_TOKENS = [
    "womens", "weird-guy", "super-guy", "easy-guy", "true-guy", "strong-guy",
    "skinny-guy", "groovy-guy", "stacked-guy", "high-skinny", "true-girl",
    "super-girl", "the-classic", "classic", "maudie", "bestie", "arrow",
    "max", "slim", "the",
]
# Trailing color/junk tokens to drop.
TAIL_TOKENS = {
    "indigo", "black", "brown", "blue", "white", "ecru", "grey", "gray", "green",
    "natural", "raw", "rinsed", "bleach", "pale", "mid", "off", "x", "navy",
    "olive", "drab", "charcoal", "beige", "copy", "pre", "order", "edition",
    "1", "2", "3", "selvedge1",
}


def material_from_handle(handle):
    h = handle
    for pre in BRAND_PREFIXES:
        if h.startswith(pre):
            h = h[len(pre):]
            break
    # strip leading fit(s)
    changed = True
    while changed:
        changed = False
        for fit in FIT_TOKENS:
            if h == fit:
                return None
            if h.startswith(fit + "-"):
                h = h[len(fit) + 1:]
                changed = True
                break
    tokens = [t for t in h.split("-") if t]
    while len(tokens) > 1 and tokens[-1] in TAIL_TOKENS:
        tokens.pop()
    if not tokens:
        return None
    return " ".join(t.capitalize() for t in tokens)


def main():
    targets = archived_jeans()
    mats = defaultdict(list)
    for (dom, handle), (url, ts) in targets.items():
        m = material_from_handle(handle)
        if m:
            mats[m].append((dom, handle, ts))
    print(f"discontinued jeans handles: {len(targets)}")
    print(f"approx distinct materials (from handles): {len(mats)}\n")
    pickle = {m: v for m, v in mats.items() if "rick" in m.lower() or "pickle" in m.lower()}
    print("=== Pickle Rick / Rick Sanchez ===")
    for m in sorted(pickle):
        print(f"  {m}  ({len(pickle[m])} fit/handle)")
    print("\n=== all approx materials (sorted) ===")
    for m in sorted(mats, key=str.lower):
        print(f"  [{len(mats[m]):2}] {m}")


if __name__ == "__main__":
    main()
