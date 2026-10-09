#!/usr/bin/env python3
"""Can a shopper actually FIND the copy? — the check that separates a real copy from a hidden one.

The picture search (lens_check.py) finds every copy of the object, including ones no shopper would ever come across.
What matters is whether the person who sees your ad, then types the product words into Amazon or Google, lands on a
cheaper copy. This script answers that from searches the run has ALREADY paid for:

  <run>/amazon/<slug>_<cc>_amazon.json   the Amazon word search per country   (amazon_check.py)
  <run>/grid/<slug>_<cc>.json            the Google Shopping word search      (shopping_grid.py)

Two steps, because a machine can't be trusted to say two photos are the same object — Claude looks:

  1) collect:  python3 visibility_check.py collect --slug loom --run <run> --countries au,us,uk,ca,de,nz
     Builds numbered sheets of the top results a shopper sees: <run>/visible/<slug>_vis_sheet.jpg (_2, _3 ...).
     LOOK at them beside the brand's photo. Costs nothing.

  2) decide:   python3 visibility_check.py decide --slug loom --run <run> --same 3,17,40
     --same = the sheet numbers that are the SAME object as the brand's product (use --same "" if none are).
     Writes <run>/visible/<slug>_visible.json, then looks up the top hidden Amazon copy in each country to get its real
     price, review count and sales badge (1 search per country, at most 6; skip with --no-lookups), then re-runs the
     map colouring (lens_check.py decide) so the colours use all of it.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import UA, fetch_json, get_serpapi_key, price_to_number, shop_listing_link  # noqa: E402

AMAZON_DOMAIN = {"au": "amazon.com.au", "us": "amazon.com", "uk": "amazon.co.uk", "ca": "amazon.ca", "de": "amazon.de", "nz": "amazon.com.au"}
CHAINS = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reference", "chains.json")))


def is_chain(source, cc):
    s = (source or "").lower()
    if re.search(r"\s-\s", s):                    # "Walmart - Some Seller" is a marketplace seller, not the chain
        return False
    return any(re.search(r"(?<![a-z0-9])" + re.escape(ch) + r"(?![a-z0-9])", s) for ch in CHAINS.get(cc, {}).get("chains", []))


def bought_number(txt):
    """'1K+ bought in past month' -> 1000 ; '300+ bought ...' -> 300 ; German '50+ Mal im letzten Monat gekauft' -> 50"""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([KkMm]?)\s*\+", txt or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", "."))
    return int(n * {"k": 1000, "m": 1000000}.get(m.group(2).lower(), 1))


def collect(a):
    out = os.path.join(a.run, "visible")
    os.makedirs(out, exist_ok=True)
    items = {}
    for cc in [c.strip().lower() for c in a.countries.split(",") if c.strip()]:
        af = os.path.join(a.run, "amazon", "%s_%s_amazon.json" % (a.slug, "au" if cc == "nz" else cc))
        if os.path.exists(af):
            for i, r in enumerate((json.load(open(af)).get("organic_results") or [])[: a.top]):
                k = "amazon:" + (r.get("asin") or r.get("title", "")[:50])
                it = items.setdefault(k, {"where": "Amazon", "source": AMAZON_DOMAIN[cc], "title": r.get("title"), "thumbnail": r.get("thumbnail"),
                                          "link": r.get("link_clean") or r.get("link"), "asin": r.get("asin"), "seen_in": {}})
                it["seen_in"][cc] = {"rank": i + 1, "price_text": r.get("price"), "reviews": r.get("reviews"), "rating": r.get("rating"),
                                     "bought": r.get("bought_last_month")}
        gf = os.path.join(a.run, "grid", "%s_%s.json" % (a.slug, cc))
        if os.path.exists(gf):
            for i, r in enumerate((json.load(open(gf)).get("shopping_results") or [])[: a.top]):
                k = "shop:%s:%s" % ((r.get("source") or "").lower(), (r.get("title") or "")[:50].lower())
                it = items.setdefault(k, {"where": "Google Shopping", "source": r.get("source"), "title": r.get("title"), "thumbnail": r.get("thumbnail"),
                                          "link": shop_listing_link(r), "asin": None, "seen_in": {}})
                it["seen_in"][cc] = {"rank": i + 1, "price_text": r.get("price"), "reviews": r.get("reviews"), "rating": r.get("rating"), "bought": None}
    order = sorted(items.values(), key=lambda it: (it["where"] != "Amazon", min(v["rank"] for v in it["seen_in"].values())))
    for i, it in enumerate(order):
        it["n"] = i

    def grab(it):
        tp = os.path.join(out, "%s_vis_thumb_%03d.jpg" % (a.slug, it["n"]))
        if it.get("thumbnail") and not os.path.exists(tp):
            try:
                req = urllib.request.Request(it["thumbnail"], headers={"User-Agent": UA})
                open(tp, "wb").write(urllib.request.urlopen(req, timeout=30).read())
            except Exception:
                pass
        it["thumb_file"] = tp if os.path.exists(tp) else None
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:          # the pictures come one by one otherwise, which takes minutes
        list(ex.map(grab, order))
    json.dump({"slug": a.slug, "top": a.top, "candidates": order}, open(os.path.join(out, "%s_vis_candidates.json" % a.slug), "w"), indent=1, ensure_ascii=False)
    try:
        from PIL import Image, ImageDraw, ImageFont
        W, cols, per = 230, 8, 40
        try:
            f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
        except Exception:
            f = ImageFont.load_default()
        pages = [order[i:i + per] for i in range(0, len(order), per)] or [[]]
        for pi, chunk in enumerate(pages):
            rows_n = (len(chunk) + cols - 1) // cols
            sheet = Image.new("RGB", (W * cols, (W + 46) * max(rows_n, 1)), "white")
            dr = ImageDraw.Draw(sheet)
            for k, c in enumerate(chunk):
                x, y = (k % cols) * W, (k // cols) * (W + 46)
                if c.get("thumb_file"):
                    try:
                        im = Image.open(c["thumb_file"]).convert("RGB")
                        sc = (W - 8) / float(max(im.width, im.height))
                        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))))
                        sheet.paste(im, (x + 4, y + 42))
                    except Exception:
                        pass
                best = min(c["seen_in"].items(), key=lambda kv: kv[1]["rank"])
                dr.text((x + 4, y + 2), "#%d %s" % (c["n"], (c["source"] or "")[:20]), fill="black", font=f)
                dr.text((x + 4, y + 21), "%s  [%s]" % (best[1].get("price_text") or "no price", ",".join(sorted(c["seen_in"]))[:17]), fill=(0, 90, 160), font=f)
            sp = os.path.join(out, "%s_vis_sheet%s.jpg" % (a.slug, "" if pi == 0 else "_%d" % (pi + 1)))
            sheet.save(sp, quality=82)
            print("what-a-shopper-sees sheet %d of %d: %s" % (pi + 1, len(pages), sp))
    except Exception as e:
        print("no sheet (%s) — open the thumbnails one by one" % str(e)[:60])
    print("results to look at:", len(order), "| now LOOK at every sheet beside the brand's photo and run: decide --same <numbers>  (or --same \"\" if none match)")


def lookups(a, out):
    """The real price, reviews and sales badge of the top hidden Amazon copy in each country (1 search each, 6 at most)."""
    lf = os.path.join(a.run, "lens", "%s_lens.json" % a.slug)
    path = os.path.join(out, "%s_lookups.json" % a.slug)
    done = json.load(open(path)) if os.path.exists(path) else {}
    if not os.path.exists(lf):
        return done
    key, _ = get_serpapi_key()
    if not key:
        return done
    used = 0
    for c in json.load(open(lf)).get("countries", []):
        cc = c["cc"]
        for h in c.get("same_object_listings") or []:
            host = (urlparse(h.get("link") or "").netloc or "").lower().replace("www.", "")
            m = re.search(r"/dp/([A-Z0-9]{10})", h.get("link") or "")
            if not m or "amazon." not in host:
                continue
            k = host + "/" + m.group(1)
            if k not in done and used < a.max_lookups:
                try:
                    q = urllib.parse.urlencode({"engine": "amazon_product", "asin": m.group(1), "amazon_domain": host, "api_key": key})
                    pr = (fetch_json("https://serpapi.com/search.json?" + q, timeout=90).get("product_results") or {})
                    done[k] = {"price_text": pr.get("price"), "reviews": pr.get("reviews"), "rating": pr.get("rating"), "bought": pr.get("bought_last_month"), "title": (pr.get("title") or "")[:90]}
                    used += 1
                    print("looked up %s: %s, %s reviews, %s" % (k, pr.get("price") or "no price", pr.get("reviews") or 0, pr.get("bought_last_month") or "no sales badge"))
                except Exception as e:
                    print("lookup failed for %s (%s)" % (k, str(e)[:60]))
            break                                 # only the first Amazon copy per country
    json.dump(done, open(path, "w"), indent=1, ensure_ascii=False)
    return done


def decide(a):
    out = os.path.join(a.run, "visible")
    data = json.load(open(os.path.join(out, "%s_vis_candidates.json" % a.slug)))
    same = set(int(x) for x in a.same.split(",") if x.strip() != "")
    # Any result that is the very same Amazon listing the picture search already confirmed is the same object, by definition.
    lf0 = os.path.join(a.run, "lens", "%s_lens.json" % a.slug)
    if os.path.exists(lf0):
        known = set()
        for c in json.load(open(lf0)).get("countries", []):
            for h in c.get("same_object_listings") or []:
                m = re.search(r"/dp/([A-Z0-9]{10})", h.get("link") or "")
                if m and not h.get("found_by_words"):
                    known.add(m.group(1))
        auto = [it["n"] for it in data["candidates"] if it.get("asin") in known and it["n"] not in same]
        if auto:
            print("added automatically (the same Amazon listing the picture search confirmed): #" + ", #".join(str(n) for n in auto))
            same |= set(auto)
    per_cc = {}
    for it in data["candidates"]:
        if it["n"] not in same:
            continue
        for cc, v in it["seen_in"].items():
            per_cc.setdefault(cc, []).append({"where": it["where"], "source": AMAZON_DOMAIN.get(cc, it["source"]) if it["where"] == "Amazon" else it["source"], "title": (it["title"] or "")[:90], "link": it["link"], "asin": it.get("asin"),
                                              "rank": v["rank"], "price_text": v.get("price_text"), "reviews": v.get("reviews"), "bought": v.get("bought"),
                                              "bought_number": bought_number(v.get("bought")), "big_chain": it["where"] != "Amazon" and is_chain(it["source"], cc),
                                              "thumb_file": it.get("thumb_file")})
    for cc in per_cc:
        per_cc[cc].sort(key=lambda h: h["rank"])
    json.dump({"slug": a.slug, "same": sorted(same), "top": data.get("top"), "countries": per_cc}, open(os.path.join(out, "%s_visible.json" % a.slug), "w"), indent=1, ensure_ascii=False)
    for cc in sorted(set(c for it in data["candidates"] for c in it["seen_in"])):
        hits = per_cc.get(cc) or []
        print("%-3s %s" % (cc, ("the copy shows up: " + "; ".join("%s result %d (%s)" % (h["where"], h["rank"], h.get("price_text") or "no price") for h in hits[:3])) if hits else "a shopper searching by words does not find the copy in the top %s" % data.get("top")))
    if not a.no_lookups:
        lookups(a, out)
    lf = os.path.join(a.run, "lens", "%s_lens.json" % a.slug)
    if os.path.exists(lf):
        L = json.load(open(lf))
        cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lens_check.py"), "decide", "--slug", a.slug, "--out", os.path.join(a.run, "lens"),
               "--same", ",".join(str(n) for n in L.get("same") or []), "--countries", ",".join(c["cc"] for c in L.get("countries") or [])]
        if L.get("brand_price"):
            cmd += ["--brand-price", str(L["brand_price"]), "--brand-currency", L.get("brand_currency") or "usd"]
        print("\nFINAL MAP COLOURS, using what a shopper can find:")
        sys.stdout.flush()
        subprocess.call(cmd)
    else:
        print("no picture-search result yet: run lens_check.py collect and decide, then run this decide again.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["collect", "decide"])
    ap.add_argument("--slug", required=True)
    ap.add_argument("--run", required=True, help="the run folder (the one that holds amazon/, grid/ and lens/)")
    ap.add_argument("--countries", default="au,us,uk,ca,de,nz")
    ap.add_argument("--top", type=int, default=12, help="how many results per search count as 'what a shopper sees'")
    ap.add_argument("--same", default="")
    ap.add_argument("--no-lookups", action="store_true")
    ap.add_argument("--max-lookups", type=int, default=6)
    a = ap.parse_args()
    collect(a) if a.mode == "collect" else decide(a)


if __name__ == "__main__":
    main()
