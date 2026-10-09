#!/usr/bin/env python3
"""Amazon check — search Amazon itself in each target country, via SerpApi (1 search per country).

Google Shopping shows Amazon as one seller among many. This looks INSIDE Amazon: how many reviews the top
listings carry, how cheap they go, how many units they say were bought last month, and whether the brand is there.

Usage: python3 amazon_check.py --slug oodie --query "wearable blanket hoodie" --brand "Oodie" \
         --countries au,us,uk,ca,de,nz --out <run>/amazon
Writes <out>/<slug>_<cc>_amazon.json (raw, cached — re-runs are free) and <out>/<slug>_amazon.json (summary).

Pressure per country:
  high    — the top listing has 5,000+ reviews, or 5+ of the first 20 listings have 1,000+ reviews
  medium  — any of the first 20 has 1,000+ reviews, or 10+ have 100+
  low     — none of the above
New Zealand has no Amazon site; it is checked against amazon.com.au (which ships to NZ) and labelled so.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse

from common import get_serpapi_key, fetch_json

DOMAINS = {"au": "amazon.com.au", "us": "amazon.com", "uk": "amazon.co.uk", "ca": "amazon.ca", "de": "amazon.de", "nz": "amazon.com.au"}
LABELS = {"au": "Australia", "us": "United States", "uk": "United Kingdom", "ca": "Canada", "de": "Germany", "nz": "New Zealand"}


def bought_number(s):
    """'1K+ bought in past month' -> 1000 ; '300+ bought...' -> 300"""
    m = re.search(r"([\d.,]+)\s*([KkMm]?)\+?\s*(bought|gekauft)", s or "")
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return int(n * {"k": 1000, "m": 1000000}.get(m.group(2).lower(), 1))


def summarise(cc, d, brand):
    rows = []
    for r in (d.get("organic_results") or [])[:20]:
        rows.append({"title": (r.get("title") or "")[:90], "price_text": r.get("price"), "price": r.get("extracted_price"),
                     "rating": r.get("rating"), "reviews": r.get("reviews") or 0, "bought_text": r.get("bought_last_month"),
                     "bought": bought_number(r.get("bought_last_month")), "sponsored": bool(r.get("sponsored")),
                     "badges": r.get("badges"), "link": r.get("link_clean") or r.get("link"), "thumbnail": r.get("thumbnail"),
                     "is_brand": bool(brand) and brand.lower() in (r.get("title") or "").lower()})
    revs = sorted((r["reviews"] for r in rows), reverse=True)
    n1000 = sum(1 for v in revs if v >= 1000)
    n100 = sum(1 for v in revs if v >= 100)
    top = revs[0] if revs else 0
    if top >= 5000 or n1000 >= 5:
        pressure = "high"
    elif n1000 >= 1 or n100 >= 10:
        pressure = "medium"
    else:
        pressure = "low"
    prices = sorted(r["price"] for r in rows if r["price"])
    bought = sum(r["bought"] or 0 for r in rows)
    best = sorted(rows, key=lambda r: r["reviews"], reverse=True)[:3]
    why = "top listing %s reviews; %d of the first %d have 1,000+" % ("{:,}".format(top), n1000, len(rows))
    if bought:
        why += "; at least %s bought last month across them" % "{:,}".format(bought)
    return {"cc": cc, "label": LABELS.get(cc, cc.upper()), "amazon_site": DOMAINS[cc],
            "note": "No Amazon site in New Zealand; this is Amazon Australia, which ships there." if cc == "nz" else None,
            "pressure": pressure, "why": why, "listings_seen": len(rows), "top_reviews": top, "n_1000_plus": n1000,
            "cheapest": prices[0] if prices else None, "typical": prices[len(prices) // 2] if prices else None,
            "bought_last_month_min": bought or None, "brand_present": any(r["is_brand"] for r in rows), "top3": best}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--brand", default="")
    ap.add_argument("--countries", default="au,us,uk,ca,de,nz")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    key, src = get_serpapi_key()
    if not key:
        print("NO-EXTRAS MODE: " + src + ". Amazon check skipped; treat Amazon pressure as an Assumption.")
        return
    out, fetched = [], {}
    for cc in [c.strip().lower() for c in a.countries.split(",") if c.strip()]:
        if cc not in DOMAINS:
            print("skip %s: no Amazon site mapped" % cc)
            continue
        dom = DOMAINS[cc]
        raw = os.path.join(a.out, "%s_%s_amazon.json" % (a.slug, cc))
        d = None
        if os.path.exists(raw):
            d = json.load(open(raw))
        elif dom in fetched:            # NZ reuses the Australian search — no extra cost
            d = fetched[dom]
        else:
            q = urllib.parse.urlencode({"engine": "amazon", "k": a.query, "amazon_domain": dom, "api_key": key})
            for attempt in range(3):
                try:
                    d = fetch_json("https://serpapi.com/search.json?" + q, timeout=120)
                    break
                except Exception as e:
                    d = {"error": str(e)[:160]}
                    time.sleep(5 * (attempt + 1))
        if d.get("error"):
            print("%-3s ERROR  %s" % (cc, d["error"]))
            out.append({"cc": cc, "label": LABELS.get(cc), "amazon_site": dom, "pressure": "error", "why": d["error"]})
            continue
        json.dump(d, open(raw, "w"))
        fetched[dom] = d
        s = summarise(cc, d, a.brand)
        out.append(s)
        print("%-3s %-6s %-14s %s%s" % (cc, s["pressure"].upper(), dom, s["why"], " | BRAND IS ON AMAZON" if s["brand_present"] else ""))
        sys.stdout.flush()
    json.dump({"slug": a.slug, "query": a.query, "brand": a.brand, "countries": out},
              open(os.path.join(a.out, "%s_amazon.json" % a.slug), "w"), indent=2, ensure_ascii=False)
    print("wrote:", os.path.join(a.out, "%s_amazon.json" % a.slug))


if __name__ == "__main__":
    main()
