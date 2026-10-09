#!/usr/bin/env python3
"""Google Shopping "as seen from" each target country, via SerpApi. ONE product per run.

Usage:
  python3 shopping_grid.py --slug bag --query "anti theft crossbody bag" --countries au,us,uk,ca,de,nz --out run1/grid [--brand-price 49.99]

For each country writes <out>/<slug>_<cc>.json (raw, cached — re-runs are free) and at the end
<out>/<slug>_grid.json (the summary the report uses). Prints one plain line per country.

Status per country:
  blocked  — a big chain (reference/chains.json) sells a listing at or under --brand-price (or any chain if no price given)
  crowded  — no chain, but 20+ distinct sellers, or cheapest < typical/3, or a marketplace is the only big name
  open     — none of the above
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
from collections import Counter

import re

from common import get_serpapi_key, fetch_json, price_to_number, SKILL_DIR

CHAINS = json.load(open(os.path.join(SKILL_DIR, "reference", "chains.json")))


def _matches(name_low, terms):
    """Whole-word match so 'mec' doesn't hit 'mecca'."""
    return any(re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", name_low) for t in terms)


def _third_party(name_low):
    """'Walmart - Seller', 'The Warehouse - Marketplace', 'Kaufland.de - modeherz' are outside sellers on a big
    site's marketplace, not the chain itself. They count as marketplace, never as chain."""
    return "marketplace" in name_low or bool(re.search(r"\s[-–]\s\S", name_low))


def classify(cc, res, brand_price):
    cfg = CHAINS[cc]
    sellers = Counter((r.get("source") or "?") for r in res)
    rows = []
    for r in res:
        src = (r.get("source") or "?")
        low = src.lower()
        rows.append({
            "seller": src, "title": (r.get("title") or "")[:90], "price_text": r.get("price"),
            "price": price_to_number(r.get("price")), "rating": r.get("rating"), "reviews": r.get("reviews"),
            "is_chain": _matches(low, cfg["chains"]) and not _third_party(low),
            "is_marketplace": _matches(low, cfg["marketplaces"]) or _third_party(low),
            "link": r.get("product_link") or r.get("link"), "thumbnail": r.get("thumbnail"),
        })
    prices = sorted(p["price"] for p in rows if p["price"])
    median = prices[len(prices) // 2] if prices else None
    cheapest = prices[0] if prices else None
    chain_rows = [r for r in rows if r["is_chain"]]
    if brand_price:
        chain_block = [r for r in chain_rows if r["price"] is not None and r["price"] <= brand_price * 1.05]
    else:
        chain_block = chain_rows
    big_names = {r["seller"] for r in rows if r["is_chain"] or r["is_marketplace"]}
    only_marketplace = bool(big_names) and not chain_rows
    if chain_block:
        status, why = "blocked", "%s sells it at %s" % (chain_block[0]["seller"], chain_block[0]["price_text"])
    elif chain_rows:
        status, why = "crowded", "%s sells a pricier version (%s)" % (chain_rows[0]["seller"], chain_rows[0]["price_text"])
    elif len(sellers) >= 20:
        status, why = "crowded", "%d different sellers" % len(sellers)
    elif cheapest and median and cheapest < median / 3:
        status, why = "crowded", "knock-offs from %s vs typical %s" % (cheapest, median)
    elif only_marketplace:
        status, why = "crowded", "only marketplaces (%s) carry it" % ", ".join(sorted(big_names))[:60]
    else:
        status, why = "open", "no chain, %d sellers" % len(sellers)
    top = max(rows, key=lambda r: (r.get("reviews") or 0), default=None)
    return {
        "cc": cc, "label": cfg["label"], "currency": cfg["currency"], "status": status, "why": why,
        "results": len(rows), "distinct_sellers": len(sellers),
        "chains_present": sorted({r["seller"] for r in chain_rows}),
        "marketplaces_present": sorted({r["seller"] for r in rows if r["is_marketplace"]}),
        "cheapest": cheapest, "typical": median,
        "most_reviewed": ({"seller": top["seller"], "title": top["title"], "reviews": top["reviews"], "price_text": top["price_text"]} if top else None),
        "top_rows": sorted(rows, key=lambda r: (r.get("reviews") or 0), reverse=True)[:8],
        "chain_rows": chain_rows[:6],
        "thin_market": len(rows) < 15,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--countries", default="au,us,uk,ca,de,nz")
    ap.add_argument("--out", required=True)
    ap.add_argument("--brand-price", type=float, default=None, help="the ad brand's price, in that country's money if known")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    key, src = get_serpapi_key()
    if not key:
        print("NO-EXTRAS MODE: " + src + ". Country grid skipped; mark retail/seller/price numbers as Assumption.")
        json.dump({"slug": a.slug, "query": a.query, "mode": "no-extras", "countries": []},
                  open(os.path.join(a.out, "%s_grid.json" % a.slug), "w"), indent=2)
        return

    summary = []
    for cc in [c.strip().lower() for c in a.countries.split(",") if c.strip()]:
        if cc not in CHAINS:
            print("skip %s: not in reference/chains.json" % cc)
            continue
        cfg = CHAINS[cc]
        raw_path = os.path.join(a.out, "%s_%s.json" % (a.slug, cc))
        data = None
        if os.path.exists(raw_path):
            data = json.load(open(raw_path))
            if data.get("error"):
                data = None
        if data is None:
            q = urllib.parse.urlencode({"engine": "google_shopping", "q": a.query, "gl": cc, "hl": cfg["hl"],
                                        "location": cfg["location"], "api_key": key})
            for attempt in range(3):
                try:
                    data = fetch_json("https://serpapi.com/search.json?" + q, timeout=120)
                    break
                except Exception as e:
                    data = {"error": str(e)[:160]}
                    time.sleep(4 * (attempt + 1))
            json.dump(data, open(raw_path, "w"))
        if data.get("error"):
            cell = {"cc": cc, "label": cfg["label"], "currency": cfg["currency"], "status": "error", "why": data["error"], "results": 0}
        else:
            cell = classify(cc, data.get("shopping_results", []), a.brand_price)
        summary.append(cell)
        print("%-3s %-8s %-3d results  %s" % (cc, cell["status"].upper(), cell.get("results", 0), cell.get("why", "")))
        sys.stdout.flush()

    out = {"slug": a.slug, "query": a.query, "mode": "full", "brand_price": a.brand_price, "countries": summary}
    json.dump(out, open(os.path.join(a.out, "%s_grid.json" % a.slug), "w"), indent=2, ensure_ascii=False)
    print("wrote:", os.path.join(a.out, "%s_grid.json" % a.slug))


if __name__ == "__main__":
    main()
