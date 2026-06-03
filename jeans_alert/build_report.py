"""Render the fabric catalog as a visual HTML report: photo cards, faceted
filters (weight / fiber / dye / theme), live search, and a click-to-zoom
lightbox that cycles through every photo of a fabric.

Active fabrics use their Shopify product images; discontinued fabrics use the
photos from their Squarespace showcase page (fetched once and cached).
Output: jeans_alert/materials.html
"""
import html
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from build_catalog import collect, weight_oz, SQ
from tags import tag_row, slug

IMG_CACHE = "jeans_alert/squarespace_images.json"
WORKERS = 8
GROUPS = [("weight", "Weight"), ("fiber", "Fiber"),
          ("dye", "Dye / finish"), ("theme", "Theme / collab")]
WEIGHT_ORDER = ["Lightweight", "Midweight", "Heavyweight", "Super-heavy", "Unknown"]


def squarespace_images(slug_, limit=6):
    page = requests.get(f"{SQ}/{slug_}", timeout=30).text
    urls = re.findall(r"https://images\.squarespace-cdn\.com/[^\"'\s)]+?\.(?:jpe?g|png|webp)",
                      page, re.I)
    out = []
    for u in dict.fromkeys(urls):
        if "logo" in u.lower():
            continue
        out.append(u.split("?")[0] + "?format=700w")
        if len(out) >= limit:
            break
    return out


def attach_images(rows):
    try:
        cache = json.load(open(IMG_CACHE, encoding="utf-8"))
    except FileNotFoundError:
        cache = {}
    # migrate old single-string cache values to lists
    cache = {k: (v if isinstance(v, list) else ([v] if v else []))
             for k, v in cache.items()}

    need = [r for r in rows if not r["images"] and r["slug"] and r["slug"] not in cache]
    print(f"fetching photos for {len(need)} discontinued fabrics...", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(squarespace_images, r["slug"]): r["slug"] for r in need}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                cache[futs[fut]] = fut.result()
            except requests.RequestException:
                cache[futs[fut]] = []
            if i % 25 == 0:
                print(f"  {i}/{len(need)}", flush=True)
    json.dump(cache, open(IMG_CACHE, "w", encoding="utf-8"), indent=0)

    for r in rows:
        if not r["images"] and r["slug"]:
            r["images"] = cache.get(r["slug"], [])
    return rows


def chips_html(rows):
    counts = {g: Counter() for g, _ in GROUPS}
    for r in rows:
        counts["weight"][r["weight"]] += 1
        for g in ("fiber", "dye", "theme"):
            for v in r[g]:
                counts[g][v] += 1
    blocks = []
    for g, label in GROUPS:
        if g == "weight":
            vals = [v for v in WEIGHT_ORDER if v in counts[g]]
        else:
            vals = [v for v, _ in counts[g].most_common()]
        chips = "".join(
            f'<button class="chip" data-group="{g}" data-val="{slug(v)}">'
            f'{html.escape(v)} <i>{counts[g][v]}</i></button>' for v in vals)
        blocks.append(f'<div class="fgroup"><span class="flabel">{label}</span>{chips}</div>')
    return "\n".join(blocks)


def cards_html(rows):
    out = []
    for r in rows:
        name = html.escape(r["name"])
        active = r["status"] == "active"
        imgs = r["images"] or []
        data_imgs = html.escape("|".join(imgs))
        # Link priority: live shop first, then Squarespace showcase, then Wayback archive.
        links = []
        if r["shop_url"]:
            links.append(f'<a href="{html.escape(r["shop_url"])}" target="_blank" rel="noopener">Shop · {r["shop_fits"]} fits</a>')
        if r["showcase_url"]:
            links.append(f'<a href="{html.escape(r["showcase_url"])}" target="_blank" rel="noopener">Showcase</a>')
        if r["archived_url"]:
            links.append(f'<a href="{html.escape(r["archived_url"])}" target="_blank" rel="noopener">Archived</a>')
        thumb = (f'<img loading="lazy" src="{html.escape(imgs[0])}" alt="{name}" '
                 f'onerror="this.closest(\'.card\').classList.add(\'noimg\')">' if imgs else "")
        meta = []
        if r["weight"] != "Unknown":
            meta.append(html.escape(r["weight"]))
        meta += [html.escape(x) for x in r["fiber"] if x != "Cotton"]
        meta += [html.escape(x) for x in r["dye"]] + [html.escape(x) for x in r["theme"]]
        chips = "".join(f'<span class="tag">{m}</span>' for m in meta)
        out.append(
            f'<figure class="card {"active" if active else "disc"}{"" if imgs else " noimg"}" '
            f'data-name="{name.lower()}" data-status="{"active" if active else "disc"}" '
            f'data-weight="{slug(r["weight"])}" data-fiber="{" ".join(slug(x) for x in r["fiber"])}" '
            f'data-dye="{" ".join(slug(x) for x in r["dye"])}" '
            f'data-theme="{" ".join(slug(x) for x in r["theme"])}" '
            f'data-imgs="{data_imgs}" data-title="{name}">'
            f'<div class="thumb">{thumb}<span class="ph">no photo</span>'
            f'{f"<span class=cnt>{len(imgs)}</span>" if len(imgs) > 1 else ""}</div>'
            f'<figcaption><span class="badge {"b-active" if active else "b-disc"}">'
            f'{"Active" if active else "Discontinued"}</span>'
            f'<h3>{name}</h3><div class="meta">{chips}</div>'
            f'<div class="links">{" ".join(links)}</div></figcaption></figure>')
    return "\n".join(out)


def render(rows):
    n_active = sum(1 for r in rows if r["status"] == "active")
    n_disc = len(rows) - n_active
    n_img = sum(1 for r in rows if r["images"])
    sub = (f'{len(rows)} fabrics · {n_active} active · {n_disc} discontinued/limited · '
           f'{n_img} with photos. Click a photo to zoom. '
           f'Sources: live shop, Squarespace fabric pages, Wayback Machine.')
    tpl = TEMPLATE
    for k, v in {"%%SUB%%": sub, "%%CHIPS%%": chips_html(rows),
                 "%%CARDS%%": cards_html(rows), "%%TOTAL%%": str(len(rows))}.items():
        tpl = tpl.replace(k, v)
    return tpl


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Naked &amp; Famous — Fabric Catalog</title>
<style>
  :root { --bg:#0f1115; --card:#191c23; --ink:#e8eaf0; --mut:#9aa3b2; --line:#272b34;
          --acc:#5b8cff; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  header { padding:24px 24px 14px; border-bottom:1px solid var(--line); position:sticky; top:0;
           background:#0f1115f5; backdrop-filter:blur(8px); z-index:20; }
  h1 { margin:0 0 6px; font-size:21px; }
  .sub { color:var(--mut); font-size:13px; }
  .controls { margin-top:13px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  input[type=search] { flex:1; min-width:220px; background:#10131a; border:1px solid var(--line);
           color:var(--ink); padding:9px 12px; border-radius:9px; font-size:14px; }
  .count { color:var(--mut); font-size:12.5px; white-space:nowrap; }
  .seg button { background:#10131a; color:var(--mut); border:1px solid var(--line);
           padding:8px 13px; cursor:pointer; font-size:13px; }
  .seg button:first-child { border-radius:9px 0 0 9px; }
  .seg button:last-child { border-radius:0 9px 9px 0; }
  .seg button.on { color:#fff; background:var(--acc); border-color:var(--acc); }
  .facets { padding:10px 24px 4px; border-bottom:1px solid var(--line); position:sticky;
            top:108px; background:#0f1115f2; backdrop-filter:blur(8px); z-index:15; }
  .fgroup { display:flex; align-items:baseline; gap:7px; flex-wrap:wrap; margin:7px 0; }
  .flabel { color:var(--mut); font-size:11px; text-transform:uppercase; letter-spacing:.6px;
            min-width:84px; }
  .chip { background:#10131a; color:#c7cdd9; border:1px solid var(--line); border-radius:999px;
          padding:4px 10px; font-size:12.5px; cursor:pointer; }
  .chip i { color:var(--mut); font-style:normal; font-size:11px; }
  .chip.on { background:var(--acc); border-color:var(--acc); color:#fff; }
  .chip.on i { color:#dbe4ff; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
          gap:16px; padding:18px 24px 70px; }
  .card { margin:0; background:var(--card); border:1px solid var(--line); border-radius:13px;
          overflow:hidden; display:flex; flex-direction:column; }
  .thumb { position:relative; aspect-ratio:1/1; background:#0c0e13; display:flex;
           align-items:center; justify-content:center; cursor:zoom-in; }
  .card.noimg .thumb { cursor:default; }
  .thumb img { width:100%; height:100%; object-fit:cover; display:block; }
  .thumb .ph { position:absolute; color:#4b5260; font-size:12px; letter-spacing:.5px;
           text-transform:uppercase; }
  .card:not(.noimg) .thumb .ph { display:none; }
  .thumb .cnt { position:absolute; right:8px; bottom:8px; background:#000a; color:#fff;
           font-size:11px; padding:2px 7px; border-radius:999px; }
  figcaption { padding:11px 12px 13px; display:flex; flex-direction:column; gap:7px; }
  h3 { margin:0; font-size:14px; font-weight:600; line-height:1.3; }
  .badge { align-self:flex-start; font-size:10px; font-weight:700; letter-spacing:.5px;
           text-transform:uppercase; padding:3px 7px; border-radius:5px; }
  .b-active { background:#16321f; color:#5fd08a; }
  .b-disc { background:#3a2a12; color:#e6a85a; }
  .meta { display:flex; flex-wrap:wrap; gap:5px; }
  .tag { font-size:10.5px; color:#aeb6c4; background:#12151c; border:1px solid var(--line);
         padding:2px 7px; border-radius:5px; }
  .links { display:flex; flex-wrap:wrap; gap:6px 12px; margin-top:2px; }
  .links a { color:var(--acc); text-decoration:none; font-size:12.5px; }
  .links a:hover { text-decoration:underline; }
  .hidden { display:none !important; }
  /* lightbox */
  #lb { position:fixed; inset:0; background:#000d; display:none; z-index:50;
        align-items:center; justify-content:center; }
  #lb.open { display:flex; }
  #lb img { max-width:90vw; max-height:82vh; border-radius:8px; box-shadow:0 10px 60px #000; }
  #lb .cap { position:fixed; top:18px; left:0; right:0; text-align:center; color:#fff;
             font-size:15px; }
  #lb .cap small { color:#9aa3b2; }
  #lb button { position:fixed; background:#ffffff14; color:#fff; border:1px solid #ffffff2e;
        width:46px; height:46px; border-radius:50%; font-size:22px; cursor:pointer; }
  #lb .x { top:16px; right:18px; }
  #lb .prev { left:18px; top:50%; transform:translateY(-50%); }
  #lb .next { right:18px; top:50%; transform:translateY(-50%); }
</style></head><body>
<header>
  <h1>Naked &amp; Famous — Complete Fabric Catalog</h1>
  <div class="sub">%%SUB%%</div>
  <div class="controls">
    <input id="q" type="search" placeholder="Search fabrics… (e.g. core, godzilla, kasuri)">
    <div class="seg" id="seg">
      <button class="on" data-f="all">All</button>
      <button data-f="active">Active</button>
      <button data-f="disc">Discontinued</button>
    </div>
    <span class="count" id="count"></span>
  </div>
</header>
<div class="facets">%%CHIPS%%</div>
<main class="grid" id="grid">
%%CARDS%%
</main>
<div id="lb"><div class="cap"></div><button class="x">×</button>
  <button class="prev">‹</button><img alt=""><button class="next">›</button></div>
<script>
  const grid=document.getElementById('grid'), q=document.getElementById('q'),
        countEl=document.getElementById('count');
  let statusF='all';
  const active={weight:new Set(),fiber:new Set(),dye:new Set(),theme:new Set()};

  function apply(){
    const term=q.value.trim().toLowerCase();
    let shown=0;
    for(const c of grid.children){
      let ok = (statusF==='all'||c.dataset.status===statusF) &&
               (!term||c.dataset.name.includes(term));
      for(const g in active){
        if(ok && active[g].size){
          const have=(c.dataset[g]||'').split(' ');
          ok = have.some(v=>active[g].has(v));
        }
      }
      c.classList.toggle('hidden', !ok);
      if(ok) shown++;
    }
    countEl.textContent = shown+' shown';
  }
  q.addEventListener('input', apply);
  document.getElementById('seg').addEventListener('click', e=>{
    if(e.target.tagName!=='BUTTON') return;
    for(const b of e.target.parentNode.children) b.classList.remove('on');
    e.target.classList.add('on'); statusF=e.target.dataset.f; apply();
  });
  for(const chip of document.querySelectorAll('.chip')){
    chip.addEventListener('click', ()=>{
      const g=chip.dataset.group, v=chip.dataset.val;
      chip.classList.toggle('on');
      active[g].has(v)?active[g].delete(v):active[g].add(v);
      apply();
    });
  }

  // lightbox
  const lb=document.getElementById('lb'), lbImg=lb.querySelector('img'),
        cap=lb.querySelector('.cap');
  let imgs=[], idx=0;
  function show(){ lbImg.src=imgs[idx];
    cap.innerHTML=lb.dataset.title+' <small>'+(idx+1)+' / '+imgs.length+'</small>'; }
  function open(card){
    imgs=(card.dataset.imgs||'').split('|').filter(Boolean);
    if(!imgs.length) return;
    idx=0; lb.dataset.title=card.dataset.title; show(); lb.classList.add('open');
  }
  grid.addEventListener('click', e=>{
    const t=e.target.closest('.thumb'); if(!t) return;
    const card=t.closest('.card'); if(card.classList.contains('noimg')) return;
    open(card);
  });
  function close(){ lb.classList.remove('open'); lbImg.src=''; }
  function step(d){ if(imgs.length){ idx=(idx+d+imgs.length)%imgs.length; show(); } }
  lb.querySelector('.x').onclick=close;
  lb.querySelector('.prev').onclick=e=>{e.stopPropagation();step(-1);};
  lb.querySelector('.next').onclick=e=>{e.stopPropagation();step(1);};
  lb.addEventListener('click', e=>{ if(e.target===lb) close(); });
  document.addEventListener('keydown', e=>{
    if(!lb.classList.contains('open')) return;
    if(e.key==='Escape') close();
    else if(e.key==='ArrowLeft') step(-1);
    else if(e.key==='ArrowRight') step(1);
  });
  apply();
</script>
</body></html>"""


if __name__ == "__main__":
    rows = attach_images(collect())
    for r in rows:                       # weight for discontinued comes from the name
        if r["weight_oz"] is None:
            r["weight_oz"] = weight_oz(r["name"])
        tag_row(r)
    out = "jeans_alert/materials.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(rows))
    n_img = sum(1 for r in rows if r["images"])
    print(f"Wrote {out}: {len(rows)} fabrics, {n_img} with photos")
