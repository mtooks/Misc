"""Render the fabric catalog as a visual HTML report: photo cards, faceted
filters (weight / fiber / dye / theme), live search, and a click-to-zoom
lightbox that cycles through every photo of a fabric.

Active fabrics use their Shopify product images; discontinued fabrics use the
photos from their Squarespace showcase page (fetched once and cached).
Output: jeans_alert/materials.html
"""
import html
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from build_catalog import collect, weight_oz, SQ
from tags import tag_row, slug
from blog_match import season_label

_HERE = os.path.dirname(os.path.abspath(__file__))
IMG_CACHE = os.path.join(_HERE, "squarespace_images.json")
WORKERS = 8
# Weight is a continuous slider (on the oz value); these three are chip facets
# tucked inside the "Filter" popover.
FILTER_GROUPS = [("fiber", "Fiber"), ("dye", "Dye / finish"),
                 ("theme", "Theme / collab")]


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
    """One column of chips per category (fiber / dye / theme), shown side by side
    inside the Filter dropdown."""
    counts = {g: Counter() for g, _ in FILTER_GROUPS}
    for r in rows:
        for g, _ in FILTER_GROUPS:
            for v in r[g]:
                counts[g][v] += 1
    blocks = []
    for g, label in FILTER_GROUPS:
        vals = [v for v, _ in counts[g].most_common()]
        chips = "".join(
            f'<button class="chip" data-group="{g}" data-val="{slug(v)}">'
            f'{html.escape(v)} <i>{counts[g][v]}</i></button>' for v in vals)
        blocks.append(f'<div class="fcol"><span class="flabel">{label}</span>'
                      f'<div class="chips">{chips}</div></div>')
    return "\n".join(blocks)


def oz_bounds(rows):
    """Min/max denim weight (oz) across fabrics with a known weight."""
    vals = [r["weight_oz"] for r in rows if r.get("weight_oz")]
    if not vals:
        return 0, 40
    import math
    return int(math.floor(min(vals))), int(math.ceil(max(vals)))


def cards_html(rows):
    out = []
    for r in rows:
        name = html.escape(r["name"])
        active = r["in_stock"]  # "available" = at least one buyable size in stock
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
        if r.get("blog_url"):
            links.append(f'<a href="{html.escape(r["blog_url"])}" target="_blank" rel="noopener">Blog</a>')
        thumb = (f'<img loading="lazy" src="{html.escape(imgs[0])}" alt="{name}" '
                 f'onerror="this.closest(\'.card\').classList.add(\'noimg\')">' if imgs else "")
        meta = []
        if r["weight_oz"]:
            meta.append(f'{r["weight_oz"]:g} oz')
        meta += [html.escape(x) for x in r["fiber"] if x != "Cotton"]
        meta += [html.escape(x) for x in r["dye"]] + [html.escape(x) for x in r["theme"]]
        chips = "".join(f'<span class="tag">{m}</span>' for m in meta)
        season = season_label(r.get("release_date"))
        rel = f'<div class="rel">Released ~{html.escape(season)}</div>' if season else ""
        data_season = slug(season) if season else ""
        data_year = (r.get("release_date") or "")[:4]
        out.append(
            f'<figure class="card {"active" if active else "disc"}{"" if imgs else " noimg"}" '
            f'data-name="{name.lower()}" data-status="{"active" if active else "disc"}" '
            f'data-weight="{slug(r["weight"])}" data-oz="{r["weight_oz"] if r["weight_oz"] else ""}" '
            f'data-fiber="{" ".join(slug(x) for x in r["fiber"])}" '
            f'data-dye="{" ".join(slug(x) for x in r["dye"])}" '
            f'data-theme="{" ".join(slug(x) for x in r["theme"])}" '
            f'data-season="{data_season}" data-year="{data_year}" '
            f'data-imgs="{data_imgs}" data-title="{name}">'
            f'<div class="thumb">{thumb}<span class="ph">no photo</span>'
            f'{f"<span class=cnt>{len(imgs)}</span>" if len(imgs) > 1 else ""}</div>'
            f'<figcaption><span class="badge {"b-active" if active else "b-disc"}">'
            f'{"Available" if active else "Unavailable"}</span>'
            f'<h3>{name}</h3>{rel}<div class="meta">{chips}</div>'
            f'<div class="links">{" ".join(links)}</div></figcaption></figure>')
    return "\n".join(out)


def render(rows):
    oz_lo, oz_hi = oz_bounds(rows)
    tpl = TEMPLATE
    for k, v in {"%%CHIPS%%": chips_html(rows),
                 "%%CARDS%%": cards_html(rows), "%%TOTAL%%": str(len(rows)),
                 "%%OZMIN%%": str(oz_lo), "%%OZMAX%%": str(oz_hi)}.items():
        tpl = tpl.replace(k, v)
    return tpl


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Naked &amp; Famous — The Archives</title>
<style>
  :root { --bg:#0f1115; --card:#191c23; --ink:#e8eaf0; --mut:#9aa3b2; --line:#272b34;
          --acc:#5b8cff; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.45 "Times New Roman",Times,serif; }
  button, input, select, textarea { font-family:inherit; }
  header { padding:24px 24px 14px; border-bottom:1px solid var(--line); position:sticky; top:0;
           background:#0f1115f5; backdrop-filter:blur(8px); z-index:20; }
  h1 { margin:0 0 6px; font-size:21px; }
  /* shared brand lockup: N&F logo — "The Archives" (Times New Roman) */
  .brand { display:flex; align-items:center; gap:13px; margin:0 0 6px; }
  .brand img { height:44px; width:auto; display:block; }
  .brand .dash { font-family:"Times New Roman",Times,serif; font-weight:400; font-size:30px;
                 color:var(--mut); line-height:1; }
  .brand .arch { font-family:"Times New Roman",Times,serif; font-weight:400; font-size:25px;
                 letter-spacing:.5px; color:var(--ink); }
  .controls { margin-top:13px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  input[type=search] { flex:1; min-width:220px; background:#10131a; border:1px solid var(--line);
           color:var(--ink); padding:9px 12px; border-radius:9px; font-size:14px; }
  .count { color:var(--mut); font-size:12.5px; white-space:nowrap; }
  .seg button { background:#10131a; color:var(--mut); border:1px solid var(--line);
           padding:8px 13px; cursor:pointer; font-size:13px; }
  .seg button:first-child { border-radius:9px 0 0 9px; }
  .seg button:last-child { border-radius:0 9px 9px 0; }
  .seg button.on { color:#fff; background:var(--acc); border-color:var(--acc); }
  .flabel { color:var(--mut); font-size:11px; text-transform:uppercase; letter-spacing:.6px; }
  /* weight range slider (dual handle, on oz) — lives in the Filter dropdown */
  .range { position:relative; width:230px; height:28px; }
  .range .track { position:absolute; top:12px; left:0; right:0; height:4px;
                  background:var(--line); border-radius:2px; }
  .range .fill { position:absolute; height:100%; background:var(--acc); border-radius:2px; }
  .range input[type=range] { position:absolute; top:0; left:0; width:100%; height:28px;
            margin:0; background:none; pointer-events:none; -webkit-appearance:none;
            appearance:none; }
  .range input[type=range]::-webkit-slider-thumb { pointer-events:auto;
            -webkit-appearance:none; appearance:none; width:16px; height:16px;
            border-radius:50%; background:var(--acc); border:2px solid #fff; cursor:pointer; }
  .range input[type=range]::-moz-range-thumb { pointer-events:auto; width:16px; height:16px;
            border-radius:50%; background:var(--acc); border:2px solid #fff; cursor:pointer; }
  .range input[type=range]::-webkit-slider-runnable-track { background:none; }
  .range input[type=range]::-moz-range-track { background:none; }
  .rangeval { color:var(--mut); font-size:12.5px; min-width:88px; white-space:nowrap; }
  /* Filter popover */
  .fbtn { background:#10131a; color:#c7cdd9; border:1px solid var(--line); border-radius:999px;
          padding:7px 14px; font-size:13px; cursor:pointer; display:inline-flex;
          align-items:center; gap:7px; }
  .fbtn:hover { border-color:var(--acc); }
  .fbtn.on { color:#fff; background:var(--acc); border-color:var(--acc); }
  .fbadge { background:#fff; color:var(--acc); border-radius:999px; font-size:11px;
            font-weight:700; min-width:18px; height:18px; padding:0 5px; display:inline-flex;
            align-items:center; justify-content:center; }
  .fbtn:not(.on) .fbadge { background:var(--acc); color:#fff; }
  .fpop { position:absolute; top:calc(100% - 1px); left:24px; right:24px; max-width:940px;
          background:#13161d; border:1px solid var(--line); border-radius:12px;
          padding:16px 18px 12px; box-shadow:0 16px 50px #000a; z-index:30; }
  .fpop-cols { display:flex; gap:30px; flex-wrap:wrap; }
  .fcol { display:flex; flex-direction:column; gap:9px; min-width:150px; }
  .fcol .chips { display:flex; flex-direction:column; align-items:flex-start; gap:6px; }
  .fcol-weight { min-width:250px; gap:12px; }
  .fpop-foot { margin-top:14px; padding-top:10px; border-top:1px solid var(--line);
               display:flex; justify-content:flex-end; }
  .fclear { background:none; border:1px solid var(--line); color:var(--mut); border-radius:8px;
            padding:6px 13px; font-size:12.5px; cursor:pointer; }
  .fclear:hover { color:var(--ink); border-color:var(--acc); }
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
  .rel { font-size:11px; color:var(--mut); margin-top:-3px; }
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
  /* --- intro: vibey scroll-snap timeline landing --- */
  #intro { position:fixed; inset:0; z-index:100; background:var(--bg); }
  #intro.out { animation:introFadeOut .55s forwards; pointer-events:none; }
  @keyframes introFadeOut { to { opacity:0; visibility:hidden; } }
  #intro-scroll { position:absolute; inset:0; overflow-y:auto; overflow-x:hidden;
                  scroll-snap-type:y mandatory; scrollbar-width:none; }
  #intro-scroll::-webkit-scrollbar { width:0; height:0; }
  .intro-hd { position:absolute; top:0; left:0; right:0; z-index:3; padding:26px 40px 34px;
              pointer-events:none; background:linear-gradient(#0f1115f2,#0f111500); }
  .intro-sub { color:var(--mut); font-size:13px; margin-top:4px; }
  #intro-hint { position:absolute; bottom:18px; left:0; right:0; text-align:center; z-index:3;
                color:var(--mut); font-size:12px; pointer-events:none; letter-spacing:.3px;
                animation:hintPulse 2.4s ease-in-out infinite; }
  @keyframes hintPulse { 0%,100%{opacity:.45} 50%{opacity:.95} }
  .s-panel { height:100%; scroll-snap-align:center; scroll-snap-stop:always;
             display:flex; align-items:stretch; }
  /* axis + labels grow on large screens (clamp min = small-screen size) */
  .s-axis { position:relative; flex:0 0 clamp(160px, 16vw, 240px); }
  .s-axis .line { position:absolute; right:22px; top:0; bottom:0; width:2px; background:var(--line); }
  .s-axis .dot { position:absolute; right:18px; top:50%; width:11px; height:11px; margin-top:-6px;
                 border-radius:50%; background:var(--acc); box-shadow:0 0 0 5px rgba(91,140,255,.16); }
  .s-axis .lbl { position:absolute; right:42px; top:50%; transform:translateY(-50%); text-align:right; }
  .s-axis .lbl b { display:block; font-size:clamp(19px, 2.4vw, 34px); font-weight:700; line-height:1.1; }
  .s-axis .lbl span { display:block; font-size:clamp(13px, 1.4vw, 20px); color:var(--mut); letter-spacing:1px; }
  .s-axis .lbl i { display:block; font-style:normal; font-size:clamp(10.5px, 1vw, 15px);
                   color:var(--mut); margin-top:4px; }
  .s-grid { flex:1; display:grid; place-content:center; gap:14px; padding:20px 40px; }
  .s-card { display:flex; flex-direction:column; gap:6px; min-width:0;
            text-decoration:none; color:inherit; transition:transform .15s; }
  a.s-card { cursor:pointer; }
  a.s-card:hover { transform:translateY(-3px); }
  a.s-card:hover .ph { box-shadow:0 0 0 2px var(--acc), 0 10px 26px #0009; }
  a.s-card:hover .nm { color:var(--acc); }
  .s-card .ph { aspect-ratio:1; border-radius:9px; overflow:hidden; background:#0c0e13;
                display:flex; align-items:center; justify-content:center; transition:box-shadow .15s; }
  .s-card img { width:100%; height:100%; object-fit:cover; display:block; }
  .s-card .nm { font-size:11px; color:var(--ink); text-align:center;
                white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .s-card .noimg-t { color:#4b5260; font-size:10px; text-transform:uppercase; letter-spacing:.5px; }
  .s-cta { height:100%; scroll-snap-align:center; display:flex; flex-direction:column;
           align-items:center; justify-content:center; gap:14px; text-align:center; padding:24px; }
  .cta-kicker { color:var(--mut); font-size:12px; letter-spacing:2px; text-transform:uppercase; }
  .s-cta h2 { margin:0; font-size:32px; font-weight:700; letter-spacing:-.5px; }
  .s-cta p { margin:0; color:var(--mut); font-size:14px; }
  #go-catalog { margin-top:8px; background:var(--acc); color:#fff; border:none; border-radius:999px;
                padding:15px 34px; font-size:16px; font-weight:600; cursor:pointer;
                box-shadow:0 10px 40px rgba(91,140,255,.35); transition:transform .15s, box-shadow .15s; }
  #go-catalog:hover { transform:translateY(-2px); box-shadow:0 14px 50px rgba(91,140,255,.5); }
</style></head><body>
<div id="intro">
  <div id="intro-scroll"></div>
  <div class="intro-hd">
    <div class="brand">
      <img src="https://nakedandfamousdenim.com/cdn/shop/files/Naked_Famous_Denim.png?v=1778706745&amp;width=480" alt="Naked &amp; Famous">
      <span class="dash">—</span><span class="arch">The Archives</span>
    </div>
  </div>
  <div id="intro-hint">scroll to wander · click a fabric to open it · click empty space to skip</div>
</div>
<header>
  <div class="brand">
    <img src="https://nakedandfamousdenim.com/cdn/shop/files/Naked_Famous_Denim.png?v=1778706745&amp;width=480" alt="Naked &amp; Famous">
    <span class="dash">—</span><span class="arch">The Archives</span>
  </div>
  <div class="controls">
    <input id="q" type="search" placeholder="Search fabrics… (e.g. core, godzilla, kasuri)">
    <div class="seg" id="seg">
      <button class="on" data-f="all">All</button>
      <button data-f="active">Available</button>
      <button data-f="disc">Unavailable</button>
    </div>
    <button class="fbtn" id="fbtn">Filter <span class="fbadge hidden" id="fbadge">0</span></button>
    <span class="count" id="count"></span>
  <div class="fpop hidden" id="fpop">
    <div class="fpop-cols">
      <div class="fcol fcol-weight">
        <span class="flabel">Weight</span>
        <div class="range" id="range">
          <div class="track"><div class="fill" id="fill"></div></div>
          <input type="range" id="wmin" min="%%OZMIN%%" max="%%OZMAX%%" step="0.5" value="%%OZMIN%%">
          <input type="range" id="wmax" min="%%OZMIN%%" max="%%OZMAX%%" step="0.5" value="%%OZMAX%%">
        </div>
        <span class="rangeval" id="wval"></span>
      </div>
      %%CHIPS%%
    </div>
    <div class="fpop-foot"><button class="fclear" id="fclear">Clear all</button></div>
  </div>
  </div>
</header>
<main class="grid" id="grid">
%%CARDS%%
</main>
<div id="lb"><div class="cap"></div><button class="x">×</button>
  <button class="prev">‹</button><img alt=""><button class="next">›</button></div>
<script>
  const grid=document.getElementById('grid'), q=document.getElementById('q'),
        countEl=document.getElementById('count');
  let statusF='all';
  const active={fiber:new Set(),dye:new Set(),theme:new Set()};

  // weight range slider (dual handle, on the oz value)
  const wmin=document.getElementById('wmin'), wmax=document.getElementById('wmax'),
        fill=document.getElementById('fill'), wval=document.getElementById('wval');
  const OZMIN=+wmin.min, OZMAX=+wmax.max, SPAN=(OZMAX-OZMIN)||1;
  function syncRange(){
    const lo=+wmin.value, hi=+wmax.value;
    fill.style.left=((lo-OZMIN)/SPAN*100)+'%';
    fill.style.right=((OZMAX-hi)/SPAN*100)+'%';
    wval.textContent=lo+'–'+hi+' oz';
  }
  wmin.addEventListener('input', ()=>{
    if(+wmin.value>+wmax.value) wmin.value=wmax.value; syncRange(); apply(); });
  wmax.addEventListener('input', ()=>{
    if(+wmax.value<+wmin.value) wmax.value=wmin.value; syncRange(); apply(); });

  function apply(){
    const term=q.value.trim().toLowerCase();
    const lo=+wmin.value, hi=+wmax.value, fullW=(lo<=OZMIN && hi>=OZMAX);
    let shown=0;
    for(const c of grid.children){
      let ok = (statusF==='all'||c.dataset.status===statusF) &&
               (!term||c.dataset.name.includes(term));
      if(ok){
        const oz=parseFloat(c.dataset.oz);
        // unknown-weight fabrics pass only while the slider spans the full range
        ok = isNaN(oz) ? fullW : (oz>=lo && oz<=hi);
      }
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

  // Filter popover (fiber / dye / theme)
  const fbtn=document.getElementById('fbtn'), fpop=document.getElementById('fpop'),
        fbadge=document.getElementById('fbadge');
  function updateBadge(){
    let n=0; for(const g in active) n+=active[g].size;
    fbadge.textContent=n; fbadge.classList.toggle('hidden', !n);
    fbtn.classList.toggle('on', !!n);
  }
  fbtn.addEventListener('click', e=>{ e.stopPropagation(); fpop.classList.toggle('hidden'); });
  fpop.addEventListener('click', e=>e.stopPropagation());
  document.addEventListener('click', ()=>fpop.classList.add('hidden'));
  for(const chip of document.querySelectorAll('.chip')){
    chip.addEventListener('click', ()=>{
      const g=chip.dataset.group, v=chip.dataset.val;
      chip.classList.toggle('on');
      active[g].has(v)?active[g].delete(v):active[g].add(v);
      updateBadge(); apply();
    });
  }
  document.getElementById('fclear').addEventListener('click', ()=>{
    for(const g in active) active[g].clear();
    for(const chip of document.querySelectorAll('.chip')) chip.classList.remove('on');
    updateBadge(); apply();
  });
  syncRange();

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
  // --- intro: vibey scroll-snap timeline landing ---
  (function(){
    const intro=document.getElementById('intro');
    const scroller=document.getElementById('intro-scroll');
    const SORD={winter:0,spring:1,summer:2,fall:3};
    const cap=s=>s.charAt(0).toUpperCase()+s.slice(1);

    // group dated cards by season slug ("spring-2019")
    const groups=new Map();
    for(const c of document.querySelectorAll('#grid .card')){
      const s=c.dataset.season;
      if(!s||!c.dataset.year) continue;
      (groups.get(s)||groups.set(s,[]).get(s)).push(c);
    }
    const seasons=[...groups.keys()].sort((a,b)=>{
      const ap=a.split('-'), bp=b.split('-');
      if(ap[1]!==bp[1]) return ap[1]<bp[1]?-1:1;     // year
      return (SORD[ap[0]]??4)-(SORD[bp[0]]??4);       // season within year
    });
    if(!seasons.length){ intro.remove(); return; }

    let done=false;
    function dismiss(){
      if(done) return; done=true; stopAuto();
      intro.classList.add('out');
      setTimeout(()=>intro.remove(), 600);
    }

    requestAnimationFrame(()=>{
      const viewH=scroller.clientHeight, vw=scroller.clientWidth;
      // axis reserve mirrors the CSS clamp(160px, 16vw, 240px)
      const AXIS=Math.min(240, Math.max(160, vw*0.16)), GAP=14,
            availW=vw-AXIS-80, availH=viewH-56;
      // cards keep the ~190px cap up to 1100px wide, then grow up to 340px on big screens
      const CAP=Math.min(340, Math.max(190, (vw-1100)*0.25+190));

      for(const key of seasons){
        const cards=groups.get(key); const N=cards.length; const kp=key.split('-');

        // pick the column count that makes the cards as large as possible while fitting
        let best={cols:1,size:0};
        for(let cols=1; cols<=N; cols++){
          const rows=Math.ceil(N/cols);
          const w=(availW-GAP*(cols-1))/cols;
          const h=(availH-GAP*(rows-1))/rows/1.2;   // reserve ~20% for the name
          const size=Math.min(w,h);
          if(size>best.size) best={cols,size};
        }
        const size=Math.max(56, Math.min(best.size, CAP));

        const panel=document.createElement('div'); panel.className='s-panel';
        panel.innerHTML=
          '<div class="s-axis"><div class="line"></div><div class="dot"></div>'+
          '<div class="lbl"><b>'+cap(kp[0])+'</b><span>'+kp[1]+'</span>'+
          '<i>'+N+' fabric'+(N>1?'s':'')+'</i></div></div>';

        const gridEl=document.createElement('div'); gridEl.className='s-grid';
        gridEl.style.gridTemplateColumns='repeat('+best.cols+','+size+'px)';
        for(const c of cards){
          const img=(c.dataset.imgs||'').split('|')[0];
          // link priority: showcase -> blog -> store -> archived (pulled from the card's own links)
          const links=[...c.querySelectorAll('.links a')];
          const pick=lbl=>{ const a=links.find(a=>a.textContent.trim().startsWith(lbl));
                            return a?a.getAttribute('href'):''; };
          const href=pick('Showcase')||pick('Blog')||pick('Shop')||pick('Archived')||'';
          const card=document.createElement(href?'a':'div'); card.className='s-card';
          if(href){ card.href=href; card.target='_blank'; card.rel='noopener'; }
          card.innerHTML='<div class="ph">'+
            (img?'<img loading="lazy" src="'+img+'" alt="">':'<span class="noimg-t">no photo</span>')+
            '</div><div class="nm"></div>';
          const nm=card.querySelector('.nm');
          nm.textContent=c.dataset.title; nm.title=c.dataset.title;
          nm.style.fontSize=Math.max(11, Math.round(size*0.085))+'px';  // scale name with card
          gridEl.appendChild(card);
        }
        panel.appendChild(gridEl);
        scroller.appendChild(panel);
      }

      // closing call-to-action panel
      const cta=document.createElement('div'); cta.className='s-cta';
      cta.innerHTML='<div class="cta-kicker">end of the line</div>'+
        '<h2>'+seasons.length+' seasons of denim.</h2>'+
        '<p>The full catalogue is searchable and filterable inside.</p>'+
        '<button id="go-catalog">Explore catalogue →</button>';
      scroller.appendChild(cta);
      document.getElementById('go-catalog')
        .addEventListener('click', e=>{ e.stopPropagation(); dismiss(); });

      startAuto();
    });

    // --- autoplay: gentle downward drift for the vibe ---
    let auto=0, lastT=0;
    const SPEED=300;  // px / second
    function frame(t){
      const dt=lastT?(t-lastT)/1000:0; lastT=t;
      scroller.scrollTop+=SPEED*dt;
      if(scroller.scrollTop+scroller.clientHeight>=scroller.scrollHeight-2){ stopAuto(); return; }
      auto=requestAnimationFrame(frame);
    }
    function startAuto(){ scroller.style.scrollSnapType='none'; lastT=0; auto=requestAnimationFrame(frame); }
    function stopAuto(){ if(auto){ cancelAnimationFrame(auto); auto=0; }
      scroller.style.scrollSnapType='y mandatory'; }

    // --- click anywhere: rush to the bottom CTA ---
    let fast=0;
    function fastToBottom(){
      stopAuto(); scroller.style.scrollSnapType='none';
      const start=scroller.scrollTop, target=scroller.scrollHeight-scroller.clientHeight;
      if(target-start<4) return;
      let t0=0; const dur=650;
      if(fast) cancelAnimationFrame(fast);
      function f(now){
        if(!t0) t0=now;
        const p=Math.min(1,(now-t0)/dur), e=1-Math.pow(1-p,3);
        scroller.scrollTop=start+(target-start)*e;
        if(p<1) fast=requestAnimationFrame(f);
        else { fast=0; scroller.style.scrollSnapType='y mandatory'; }
      }
      fast=requestAnimationFrame(f);
    }

    // user grabs the wheel/keys -> stop autoplay, hand over to snappy native scroll
    ['wheel','touchstart','keydown'].forEach(ev=>
      scroller.addEventListener(ev, ()=>{ if(auto) stopAuto(); }, {passive:true}));
    scroller.addEventListener('click', e=>{
      if(e.target.closest('a')||e.target.closest('#go-catalog')) return;  // let fabric links / CTA work
      fastToBottom();
    });
  })();

  apply();
</script>
</body></html>"""


if __name__ == "__main__":
    rows = attach_images(collect())
    for r in rows:
        # weight: shop oz (already set) -> shop+blog description -> name
        if r["weight_oz"] is None:
            r["weight_oz"] = weight_oz(r.get("desc", "")) or weight_oz(r["name"])
        tag_row(r, r.get("desc", ""))    # enrich fiber/dye/theme from descriptions
    out = os.path.join(_HERE, "materials.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(rows))

    # machine-readable export (drops the internal `desc` blob)
    fields = ("name", "status", "in_stock", "release_date", "weight_oz", "weight",
              "fiber", "dye", "theme", "shop_url", "showcase_url", "blog_url",
              "archived_url")
    meta = [{k: r.get(k) for k in fields}
            | {"season": season_label(r.get("release_date"))} for r in rows]
    with open(os.path.join(_HERE, "materials.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    n_img = sum(1 for r in rows if r["images"])
    n_dated = sum(1 for r in rows if r.get("release_date"))
    print(f"Wrote {out}: {len(rows)} fabrics, {n_img} with photos, {n_dated} dated")
