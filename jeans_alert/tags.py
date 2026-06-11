"""Derive browsing facets for each fabric from its name (+ weight from oz).

Facets: weight class, fiber/blend, dye/finish, theme/collab.
Everything is name-based (works for active + discontinued alike); weight uses the
oz value parsed from the product description when available, else 'Unknown'.
"""
import re

WEIGHT_BUCKETS = [("Lightweight", 0, 12), ("Midweight", 12, 16),
                  ("Heavyweight", 16, 21), ("Super-heavy", 21, 99)]

# (label, regex) — first match wins for weight; all matches kept for the rest.
FIBER_RULES = [
    ("Hemp", r"hemp"),
    ("Linen", r"linen"),
    ("Cashmere", r"cashmere"),
    ("Silk", r"\bsilk\b"),
    ("Wool", r"wool|tweed"),
    ("Foxfibre", r"foxfibre|fox ?fibre|foxfiber"),
    ("Recycled", r"recycled|sakiori|salvaged|upcycl"),
    ("Organic", r"organic"),
    ("Synthetic / tech", r"cordura|nylon|polyester|tech denim|active motion|ultralight"),
]
DYE_RULES = [
    # color-prefixed "core" only — bare "core"/"fade" appear in generic denim prose
    ("Colored core", r"(?:red|blue|green|black|white|gold|pink|purple|grey|gray|natural|colou?red)[ -]?core|gradient"),
    ("Natural indigo", r"natural indigo|tennen ai|aizome"),
    ("Plant / persimmon dye", r"kakishibu|catechu|turmeric|matcha|coffee|\btea\b|hiba|cypress|botanical"),
    ("Coated / waxed", r"\bwax|coated|coating|sumi"),
    ("Glow-in-the-dark", r"glow"),
    ("Scented", r"scratch|sniff|scent"),
    ("Fade-reveal", r"secret agent|fingerprint"),
]
THEME_RULES = [
    ("Godzilla", r"godzilla|ghidorah|hedorah|kaiju"),
    ("DC Comics", r"batman|joker|harley quinn|\bbane\b|dark knight|gotham"),
    ("Rick & Morty", r"\brick\b|morty|pickle|poopy|solenya|sanchez|wubba"),
    ("JoJo", r"jojo|joestar|giorno|giovanna|josuke|jolyne|jotaro|kujo|higashikata"),
    ("Dragon Ball", r"\bgoku\b|\bsaiyan\b|trunks future|\bmajin\b|\bvegeta\b|\bgohan\b"),
    ("Ghostbusters", r"ghostbuster|slimer"),
    ("Horror / slasher", r"friday the 13th|jason|voorhees|nightmare|freddy|krueger|"
                         r"leatherface|texas chainsaw|michael myers|halloween|elvira|toxic avenger"),
    ("The Matrix", r"matrix"),
    ("Chinese New Year", r"chinese new year|\bcny\b|year of|metal ox|metal rat|"
                         r"water rabbit|water tiger"),
]


def weight_class(oz):
    if not oz:
        return "Unknown"
    for label, lo, hi in WEIGHT_BUCKETS:
        if lo <= oz < hi:
            return label
    return "Unknown"


def _matches(name, rules):
    n = name.lower()
    return [label for label, pat in rules if re.search(pat, n)]


def fibers(name):
    return _matches(name, FIBER_RULES) or ["Cotton"]


def dyes(name):
    return _matches(name, DYE_RULES)


def themes(name):
    return _matches(name, THEME_RULES)


def slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def tag_row(row, text=None):
    """Attach faceting tags to a row dict in place.

    `text` (optional) is extra description — the shop product body — matched
    alongside the name so composition/finish the name omits still surface
    (e.g. "62% cotton 38% linen" -> Linen). Themes stay NAME-only: collab fabrics
    are named after the collab, and prose mentions (a "halloween" release note, a
    "vegetable-tanned" patch) otherwise cause false theme hits. Callers passing
    only `row` keep the original name-only behavior for everything.
    """
    blob = row["name"] if text is None else f"{row['name']} {text}"
    row["weight"] = weight_class(row.get("weight_oz"))
    row["fiber"] = fibers(blob)
    row["dye"] = dyes(blob)
    row["theme"] = themes(row["name"])
    return row
