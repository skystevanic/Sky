#!/usr/bin/env python3
"""What does it cost to BUY this product? — the supply side of the report.

The shops map answers "who would I compete with?". This answers the other half a dropshipper needs:
"can I get it, and what is left after I pay for it?". It costs no searches: the picture search (lens_check.py) has already
found the supplier listings (AliExpress, Alibaba, DHgate, Made-in-China, 1688, CJ Dropshipping). Supplier sites do not
show prices to Google and block automatic readers, so the PRICE is read by a person or by an assistant with a browser.

  1) list:   python3 supplier_check.py list --slug loom --run <run> --brand-price 85 --brand-currency usd
     Lists the supplier listings that are the SAME object (the numbers you gave lens_check.py decide --same), numbered.
     Writes <run>/supplier/<slug>_supplier.json.

  2) price:  python3 supplier_check.py price --slug loom --run <run> --n 1 --price 8.40 --currency usd [--shipping 3.10] [--note "min. order 1"]
     Record what listing number 1 really costs (open the link, pick the same variant, read the price and the shipping
     to the member's country). Do this for 2 or 3 listings. AliExpress is the one a dropshipper can order from one at a
     time; Alibaba and Made-in-China prices are for bulk orders, so say so in --note.

  2b) add:   python3 supplier_check.py add --slug loom --run <run> --site AliExpress --link "<listing address>" --title "..." --price 8.40 --currency usd --shipping 3.10
     When the picture search found no supplier listing (or none on AliExpress), search AliExpress yourself with the link that
     'list' prints, find the SAME object by its picture, and add it here. Only add a listing you have looked at.

  3) show:   python3 supplier_check.py show --slug loom --run <run>
     Prints the summary the report uses: cheapest delivered cost, margin at the brand's price, and the most you can
     pay to win a sale before you lose money.

If the picture search found NO supplier listing, that is a finding too: the product may be custom-made, and a beginner
may not be able to source it. The report says so.
"""
import argparse
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SITES = (("aliexpress.", "AliExpress", "single orders"), ("cjdropshipping.", "CJ Dropshipping", "single orders"), ("dhgate.", "DHgate", "small orders"),
         ("banggood.", "Banggood", "single orders"), ("alibaba.", "Alibaba", "bulk orders"), ("made-in-china.", "Made-in-China", "bulk orders"),
         ("1688.", "1688", "bulk orders, China only"), ("globalsources.", "Global Sources", "bulk orders"))
PER_USD = {"usd": 1.0, "aud": 1.5, "cad": 1.37, "gbp": 0.75, "eur": 0.86, "nzd": 1.68}     # rough; only to compare a cost with a price
NOT_A_LISTING = ("/w/wholesale", "/category/", "/wholesale/", "/showroom/", "/popular/", "/af/", "/g/", "/products-search/", "/countrysearch/", "/hot-china-products/", "/trade/search")


def site_of(link):
    host = (urlparse(link or "").netloc or "").lower()
    for key, nice, how in SITES:
        if key in host:
            return nice, how
    return None, None


def path_of(a):
    d = os.path.join(a.run, "supplier")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "%s_supplier.json" % a.slug)


def summarise(d):
    bp = d.get("brand_price")
    bp_usd = (bp / PER_USD.get((d.get("brand_currency") or "usd").lower(), 1.0)) if bp else None
    priced = []
    for l in d["listings"]:
        if l.get("price") is not None:
            cost = (l["price"] + (l.get("shipping") or 0)) / PER_USD.get((l.get("currency") or "usd").lower(), 1.0)
            l["delivered_cost_usd"] = round(cost, 2)
            priced.append(l)
    single = [l for l in priced if "bulk" not in (l.get("order_type") or "")] or priced
    best = min(single, key=lambda l: l["delivered_cost_usd"]) if single else None
    s = {"found": len(d["listings"]), "priced": len(priced), "brand_price_usd": round(bp_usd, 2) if bp_usd else None}
    if not d["listings"]:
        s["status"], s["plain"] = "none found", "The photo search did not turn up a supplier listing for this exact object. That does not prove there isn't one: search AliExpress for it by name or picture before you decide."
    elif not best:
        s["status"], s["plain"] = "found, price not read", "%d supplier listing%s found. Open them to read the price: supplier sites do not show prices to search engines." % (len(d["listings"]), "" if len(d["listings"]) == 1 else "s")
    else:
        s["status"] = "priced"
        s["cost_usd"], s["cost_site"], s["cost_includes_shipping"] = best["delivered_cost_usd"], best["site"], best.get("shipping") is not None
        if bp_usd:
            s["margin_pct"] = int(round(100 * (bp_usd - best["delivered_cost_usd"]) / bp_usd))
            s["room_per_sale_usd"] = round(bp_usd - best["delivered_cost_usd"], 2)
            s["plain"] = "%s sells it for about US$%.0f%s. At the brand's price of about US$%.0f that leaves about US$%.0f a sale (%d%%) to cover ads, payment fees and profit." % (
                best["site"], best["delivered_cost_usd"], " delivered" if s["cost_includes_shipping"] else " before shipping", bp_usd, s["room_per_sale_usd"], s["margin_pct"])
        else:
            s["plain"] = "%s sells it for about US$%.0f." % (best["site"], best["delivered_cost_usd"])
    d["summary"] = s
    return d


def do_list(a):
    cf = os.path.join(a.run, "lens", "%s_candidates.json" % a.slug)
    lf = os.path.join(a.run, "lens", "%s_lens.json" % a.slug)
    if not (os.path.exists(cf) and os.path.exists(lf)):
        print("Run lens_check.py collect and decide first: the supplier listings come from the picture search.")
        return
    same = set(json.load(open(lf)).get("same") or [])
    old = json.load(open(path_of(a))) if os.path.exists(path_of(a)) else {"listings": []}
    kept = {l["link"]: l for l in old.get("listings", [])}
    listings = []
    for c in json.load(open(cf))["candidates"]:
        site, how = site_of(c.get("link"))
        if not site or c["n"] not in same or any(x in (c.get("link") or "") for x in NOT_A_LISTING):
            continue
        prev = kept.get(c["link"], {})
        pt = next((v.get("price_text") for v in c["seen_in"].values() if v.get("price_text")), None)
        listings.append({"n": len(listings) + 1, "site": site, "order_type": how, "title": (c.get("title") or "")[:100], "link": c["link"], "thumb_file": c.get("thumb_file"),
                         "price_seen_in_search": pt, "price": prev.get("price"), "currency": prev.get("currency"), "shipping": prev.get("shipping"), "note": prev.get("note")})
    listings.sort(key=lambda l: ("bulk" in l["order_type"], l["site"]))
    for i, l in enumerate(listings, 1):
        l["n"] = i
    import urllib.parse as _u
    words = (a.words or old.get("words") or "").strip()
    d = summarise({"slug": a.slug, "brand_price": a.brand_price if a.brand_price else old.get("brand_price"), "brand_currency": a.brand_currency or old.get("brand_currency") or "usd",
                   "words": words, "aliexpress_search": ("https://www.aliexpress.com/w/wholesale-%s.html" % _u.quote(words.replace(" ", "-"))) if words else None, "listings": listings})
    json.dump(d, open(path_of(a), "w"), indent=1, ensure_ascii=False)
    if not listings:
        print("NO SUPPLIER LISTING FOUND for this object. If you marked supplier pictures as 'not the same', check them again; otherwise this is a real finding.")
    for l in listings:
        print("#%d  %-16s %-13s %s\n     %s%s" % (l["n"], l["site"], "(" + l["order_type"] + ")", l["title"][:70], l["link"], ("   [search showed " + l["price_seen_in_search"] + "]") if l["price_seen_in_search"] else ""))
    if a.words:
        import urllib.parse as _u
        print("\nSearch AliExpress yourself: https://www.aliexpress.com/w/wholesale-%s.html" % _u.quote(a.words.strip().replace(" ", "-")))
    if listings:
        print("\nNow read the real price of 2 or 3 of these (AliExpress first) and record each with:  supplier_check.py price --slug %s --run <run> --n <number> --price <amount> --currency usd --shipping <amount>" % a.slug)
    print("wrote:", path_of(a))


def do_price(a):
    d = json.load(open(path_of(a)))
    hit = [l for l in d["listings"] if l["n"] == a.n]
    if not hit:
        print("No listing number %d. Run 'list' to see the numbers." % a.n)
        return
    hit[0].update({"price": a.price, "currency": a.currency, "shipping": a.shipping, "note": a.note})
    json.dump(summarise(d), open(path_of(a), "w"), indent=1, ensure_ascii=False)
    print(d["summary"]["plain"])


def do_add(a):
    d = json.load(open(path_of(a))) if os.path.exists(path_of(a)) else {"slug": a.slug, "brand_price": a.brand_price, "brand_currency": a.brand_currency or "usd", "listings": []}
    if a.brand_price:
        d["brand_price"], d["brand_currency"] = a.brand_price, a.brand_currency or d.get("brand_currency") or "usd"
    site, how = site_of(a.link)
    d["listings"].append({"n": len(d["listings"]) + 1, "site": a.site or site or "Supplier", "order_type": how or "single orders", "title": (a.title or "")[:100], "link": a.link, "thumb_file": None,
                          "price_seen_in_search": None, "price": a.price, "currency": a.currency, "shipping": a.shipping, "note": a.note, "added_by_hand": True})
    json.dump(summarise(d), open(path_of(a), "w"), indent=1, ensure_ascii=False)
    print(d["summary"]["plain"])


def do_show(a):
    d = summarise(json.load(open(path_of(a))))
    json.dump(d, open(path_of(a), "w"), indent=1, ensure_ascii=False)
    print(d["summary"]["status"].upper(), "|", d["summary"]["plain"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["list", "price", "add", "show"])
    ap.add_argument("--slug", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--brand-price", type=float, default=None)
    ap.add_argument("--brand-currency", default=None, choices=sorted(PER_USD))
    ap.add_argument("--n", type=int)
    ap.add_argument("--price", type=float)
    ap.add_argument("--currency", default="usd", choices=sorted(PER_USD))
    ap.add_argument("--shipping", type=float, default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument("--words", default="", help="the product words, to print a ready-made AliExpress search link")
    ap.add_argument("--site", default=None)
    ap.add_argument("--link", default=None)
    ap.add_argument("--title", default=None)
    a = ap.parse_args()
    {"list": do_list, "price": do_price, "add": do_add, "show": do_show}[a.mode](a)


if __name__ == "__main__":
    main()
