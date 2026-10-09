#!/usr/bin/env python3
"""Google results "as is" — what a shopper in the target country actually sees for the category keyword.

For each country: one plain Google search via SerpApi (1 search each), then
  - the top organic results, the "People also ask" questions, the popular-products strip and any AI overview
    are saved as data  ->  <out>/<slug>_<cc>_serp.json
  - the REAL results page SerpApi fetched is rendered to a picture with Chrome  ->  <out>/<slug>_<cc>_asis.png
    (scripts stripped, 20-second load limit; falls back to data-only if Chrome is missing)

Usage: python3 google_asis.py --slug bag --query "anti theft crossbody bag" --countries au,us,uk,ca,de,nz --out <run>/asis
Re-runs reuse saved files (no new searches).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from urllib.parse import urlparse

from common import get_serpapi_key, fetch_json, chrome_path, run_chrome, SKILL_DIR, UA

CHAINS = json.load(open(os.path.join(SKILL_DIR, "reference", "chains.json")))
FORUMS = ("reddit.", "quora.", "productreview.", "whirlpool.", "trustpilot.", "youtube.", "tiktok.", "facebook.", "instagram.", "pinterest.")


def kind_of(link, cc):
    host = (urlparse(link or "").netloc or "").lower()
    cfg = CHAINS.get(cc, {"chains": [], "marketplaces": []})
    if any(re.search(r"(?<![a-z0-9])" + re.escape(c.replace(" ", "")) + r"(?![a-z0-9])", host.replace("-", "")) or c.replace(" ", "") in host.replace("-", "") for c in cfg["chains"]):
        return "big chain"
    if any(m.replace(" ", "") in host.replace("-", "") for m in cfg["marketplaces"]):
        return "marketplace"
    if any(f in host for f in FORUMS):
        return "forum / social"
    path = (urlparse(link or "").path or "").lower()
    if re.search(r"/(blog|news|guide|best|review|article)", path) or re.search(r"\bbest\b", path):
        return "article"
    return "store / brand"


def _unescape(v):
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)),
                  re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), v))


def restore_images(s):
    """Google fills product thumbnails with scripts. We strip scripts (they hang headless Chrome), so first copy
    the pictures those scripts would have set straight onto the <img> tags:
      1) var s='data:image/...';var ii=['dimg_1','dimg_2'];   (picture data sitting inside a script)
      2) google.ldi={"dimg_3":"https://encrypted-tbn0.gstatic.com/..."}   (addresses to load later)"""
    src = {}
    for data, ids in re.findall(r"var s='(data:image/[a-z+]+;base64,[^']+)';\s*var ii=\[([^\]]+)\]", s):
        for i in re.findall(r"'([^']+)'", ids):
            src[i] = _unescape(data)
    for block in re.findall(r"google\.ldi=\{(.*?)\};", s, flags=re.S):
        for i, url in re.findall(r'"([^"]+)":"([^"]+)"', block):
            src.setdefault(i, _unescape(url))
    if not src:
        return s

    def fix(m):
        tag = m.group(0)
        mid = re.search(r'\bid="([^"]+)"', tag)
        if not mid or mid.group(1) not in src:
            return tag
        real = src[mid.group(1)].replace('"', "&quot;")
        if re.search(r'\bsrc="[^"]*"', tag):
            return re.sub(r'\bsrc="[^"]*"', 'src="%s"' % real.replace("\\", "\\\\"), tag, count=1)
        return tag[:-1] + ' src="%s">' % real
    return re.sub(r"<img\b[^>]*>", fix, s)


def screenshot(html_path, png_path):
    cp = chrome_path()
    if not cp:
        return "Chrome not found — picture skipped"
    s = open(html_path, "rb").read().decode("utf-8", "replace")
    s = restore_images(s)
    s = re.sub(r"<script\b[^>]*>.*?</script>", "", s, flags=re.S | re.I)
    nojs = html_path.replace(".html", ".nojs.html")
    open(nojs, "w", encoding="utf-8").write(s)
    res = run_chrome(["--hide-scrollbars", "--timeout=15000", "--window-size=1000,2400", "--screenshot=" + png_path, "file://" + os.path.abspath(nojs)], png_path, max_wait=45)
    for junk in (nojs, html_path):                      # keep the picture and the data, not megabytes of saved web page
        try:
            os.remove(junk)
        except Exception:
            pass
    return res if res == "ok" else "Chrome could not render the page"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--countries", default="au,us,uk,ca,de,nz")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    key, src = get_serpapi_key()
    if not key:
        print("NO-EXTRAS MODE: " + src + ". 'As is' pages skipped.")
        return
    results = []
    for cc in [c.strip().lower() for c in a.countries.split(",") if c.strip()]:
        cfg = CHAINS.get(cc)
        if not cfg:
            print("skip %s: not in reference/chains.json" % cc)
            continue
        print("%s: searching and taking the picture (about 20 seconds)..." % cc.upper())
        sys.stdout.flush()
        base = os.path.join(a.out, "%s_%s" % (a.slug, cc))
        jpath, hpath, ppath = base + "_serp.json", base + "_page.html", base + "_asis.png"
        if os.path.exists(jpath):
            d = json.load(open(jpath))
        else:
            q = urllib.parse.urlencode({"engine": "google", "q": a.query, "gl": cc, "hl": cfg["hl"], "location": cfg["location"],
                                        "num": 10, "device": "desktop", "api_key": key})
            try:
                d = fetch_json("https://serpapi.com/search.json?" + q, timeout=120)
            except Exception as e:
                print(cc, "search failed:", str(e)[:120])
                continue
            json.dump(d, open(jpath, "w"))
        raw = (d.get("search_metadata") or {}).get("raw_html_file")
        if raw and not os.path.exists(hpath) and not os.path.exists(ppath):
            try:
                req = urllib.request.Request(raw, headers={"User-Agent": UA})
                open(hpath, "wb").write(urllib.request.urlopen(req, timeout=120).read())
            except Exception as e:
                print(cc, "page download failed:", str(e)[:100])
        pic = "cached" if os.path.exists(ppath) else (screenshot(hpath, ppath) if os.path.exists(hpath) else "no page")
        top = []
        # who SELLS or reviews it: skip YouTube / Instagram / Reddit style results, keep the first five others
        sellers_first = [r for r in (d.get("organic_results") or []) if kind_of(r.get("link"), cc) != "forum / social"]
        for r in sellers_first[:5]:
            top.append({"position": r.get("position"), "title": r.get("title"), "link": r.get("link"),
                        "domain": urlparse(r.get("link") or "").netloc.replace("www.", ""), "kind": kind_of(r.get("link"), cc),
                        "snippet": (r.get("snippet") or "")[:160]})
        popular = [{"title": (x.get("title") or "")[:60], "price": x.get("price"), "source": x.get("source")} for x in (d.get("immersive_products") or [])[:10]]
        ai = d.get("ai_overview") or {}
        ai_text = " ".join(b.get("snippet", "") for b in (ai.get("text_blocks") or []) if b.get("snippet"))[:600] if isinstance(ai, dict) else ""
        summary = {
            "cc": cc, "label": cfg["label"], "query": a.query, "image": ppath if os.path.exists(ppath) else None, "picture": pic,
            "top5": top, "paa": [p.get("question") for p in (d.get("related_questions") or [])[:6]],
            "popular_products": popular, "ads_on_top": [(x.get("title") or "")[:60] for x in (d.get("ads") or [])[:4]],
            "ai_overview": ai_text, "blocks": [k for k in d.keys() if k not in ("search_metadata", "search_parameters", "search_information", "pagination", "serpapi_pagination")],
        }
        results.append(summary)
        print("%s  picture: %s  | top 5: %s" % (cc.upper(), pic, "; ".join("%s (%s)" % (t["domain"], t["kind"]) for t in top)))
        print("     people ask:", " | ".join(summary["paa"][:4]))
        print("     popular products from:", ", ".join(sorted({p["source"] for p in popular if p.get("source")})[:8]))
        sys.stdout.flush()
    json.dump({"slug": a.slug, "query": a.query, "countries": results}, open(os.path.join(a.out, "%s_asis.json" % a.slug), "w"), indent=2, ensure_ascii=False)
    print("wrote:", os.path.join(a.out, "%s_asis.json" % a.slug))


if __name__ == "__main__":
    main()
