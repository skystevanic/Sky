#!/usr/bin/env python3
"""Picture search — where is the SAME OBJECT sold, country by country? (Google Lens via SerpApi, 1 search per country.)

Word searches answer "does this category exist?" (always yes). This answers "is THIS product already on a shelf here?",
which is what the map should show.

Two steps, because a machine can't be trusted to say two photos are the same object — Claude looks:

  1) collect:  python3 lens_check.py collect --slug loom --image-url <public image address of the brand's product> \
                   --brand-domain knitmend.com --countries au,us,uk,ca,de,nz --out <run>/lens
     Saves the raw results, lists every PRICED match (a real listing, not a blog), downloads thumbnails and builds
     <out>/<slug>_sheet.jpg — a numbered contact sheet. LOOK at it next to the brand's photo.

  2) decide:   python3 lens_check.py decide --slug loom --same 0,3,4,9 --brand-price 85 --brand-currency usd --out <run>/lens
     --same = the sheet numbers that are the SAME object (same mould; colour and logo don't count as different).
     Writes <out>/<slug>_lens.json with a status per country:
        red    the same object is sold by a big chain there (reference/chains.json)
        amber  the same object is on Temu, in a local shop, or on Amazon/eBay clearly cheaper than the brand
        light green ("weak")  copies exist but only weak ones: far-away marketplaces like AliExpress (slow delivery),
               or Amazon/eBay at about the brand's price (70% of it or more). Needs --brand-price to judge Amazon/eBay.
        green  the picture search found nobody but the brand selling it there
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from urllib.parse import urlparse

from common import get_serpapi_key, fetch_json, price_to_number, SKILL_DIR, UA

CHAINS = json.load(open(os.path.join(SKILL_DIR, "reference", "chains.json")))
LENS_CC = {"uk": "gb"}
NOT_SHOPS = ("reddit.", "facebook.", "instagram.", "tiktok.", "youtube.", "pinterest.", "x.com", "twitter.", "minea.", "shop.app")


def _has(name_low, terms):
    flat = re.sub(r"[^a-z0-9]", "", name_low)
    return any(re.sub(r"[^a-z0-9]", "", t) and (re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", name_low) or re.sub(r"[^a-z0-9]", "", t) == flat) for t in terms)


def kind(source, link, cc, brand_domain):
    host = (urlparse(link or "").netloc or "").lower().replace("www.", "")
    low = (source or "").lower()
    if brand_domain and brand_domain.split(".")[0] in host.replace("-", ""):
        return "the brand"
    if any(n in host for n in NOT_SHOPS):
        return "not a shop"
    cfg = CHAINS.get(cc, {})
    if _has(low, cfg.get("chains", [])) or _has(host.split(".")[0], cfg.get("chains", [])):
        return "big chain"
    allm = set(m for c in CHAINS.values() if isinstance(c, dict) for m in c.get("marketplaces", []))
    if _has(low, allm) or any(re.sub(r"[^a-z0-9]", "", m) in host.replace("-", "") for m in allm):
        return "marketplace"
    return "other store"


TLD_CC = [(".com.au", "au"), (".net.au", "au"), (".au", "au"), (".co.uk", "uk"), (".uk", "uk"), (".co.nz", "nz"), (".nz", "nz"), (".ca", "ca"), (".de", "de"), (".at", "de")]


def shop_country(link):
    """Which country a shop's web address belongs to, or None for a worldwide .com style address."""
    host = (urlparse(link or "").netloc or "").lower()
    for tld, cc in TLD_CC:
        if host.endswith(tld):
            return cc
    return None


WORLDWIDE = ("aliexpress.", "temu.", "dhgate.", "alibaba.", "shein.")          # ship to every country
HOME_OF = {"amazon.com": "us", "walmart.com": "us", "target.com": "us", "ebay.com": "us", "etsy.com": None}

# --- the fourth colour: LIGHT GREEN = "only weak copies" -------------------------------------------------------------
# A copy is WEAK when a shopper in that country is unlikely to pick it over the brand:
#   - it sits on a far-away marketplace with slow delivery (AliExpress, DHgate, Alibaba), or
#   - it is on Amazon / eBay / another marketplace but at 70% or more of the brand's price (not much cheaper).
# A copy is STRONG (the country stays amber) when it is on Temu or Shein (they advertise hard and deliver in about a week),
# in a local shop, clearly cheaper than the brand, or on a marketplace with no price showing (we can't tell, so we stay careful).
FAR_AWAY = ("aliexpress.", "dhgate.", "alibaba.", "made-in-china.")
SUPPLIER_SITES = ("aliexpress.", "dhgate.", "alibaba.", "made-in-china.", "1688.", "cjdropshipping.", "globalsources.", "banggood.")
FAST_CHEAP = ("temu.", "shein.")
WEAK_PRICE_SHARE = 0.70
# Rough money rates against the US dollar. Only used to tell "much cheaper" from "about the same", so rough is fine.
PER_USD = {"usd": 1.0, "aud": 1.5, "cad": 1.37, "gbp": 0.75, "eur": 0.86, "nzd": 1.68}
MONEY_OF = {"us": "usd", "au": "aud", "ca": "cad", "uk": "gbp", "de": "eur", "nz": "nzd"}


def brand_price_in(cc, brand_price, brand_currency):
    """The brand's price turned into that country's money (roughly). None when we were not told the price."""
    if not brand_price:
        return None
    usd = brand_price / PER_USD.get((brand_currency or "usd").lower(), 1.0)
    return usd * PER_USD[MONEY_OF.get(cc, "usd")]


def copy_strength(h, local_brand_price):
    """('weak' or 'strong', short reason) for one same-object listing."""
    host = (urlparse(h.get("link") or "").netloc or "").lower().replace("www.", "")
    if any(w in host for w in FAR_AWAY):
        return "weak", "far-away marketplace, slow delivery"
    if any(w in host for w in FAST_CHEAP):
        return "strong", "Temu or Shein"
    if h.get("kind") != "marketplace":
        return "strong", "a local shop"
    pr = price_to_number(h.get("price_text"))
    if pr is None or not local_brand_price:
        return "strong", "no price to compare"
    if pr < WEAK_PRICE_SHARE * local_brand_price:
        return "strong", "much cheaper than the brand"
    return "weak", "about the brand's price"


CREDIBLE_REVIEWS = 100          # an Amazon listing with this many reviews (or a "bought in past month" badge of 100+) is one shoppers trust


def tidy_source(source, link):
    """Google sometimes returns a page title as the shop name ('– Buy with free shipping on aliexpress')."""
    host = (urlparse(link or "").netloc or "").lower()
    for word, nice in (("aliexpress", "AliExpress"), ("temu.", "Temu"), ("dhgate", "DHgate"), ("alibaba", "Alibaba"), ("shein", "Shein")):
        if word in host:
            return nice
    return source


def _num(x):
    try:
        return int(float(str(x).replace(",", "").replace("+", "")))
    except Exception:
        return 0


def _bought(txt):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([KkMm]?)\s*\+", txt or "")
    if not m:
        return 0
    return int(float(m.group(1).replace(",", ".")) * {"k": 1000, "m": 1000000}.get(m.group(2).lower(), 1))


def findable_strength(h, local_brand_price):
    """The rule once we know what a shopper can FIND (visibility_check.py has run).
    A REAL copy is one a shopper will come across or trust, AND that is clearly cheaper than the brand:
      - it shows in the top word-search results on Amazon or Google Shopping in that country (if it is also trusted, it counts
        even at the brand's price), or
      - it is an Amazon listing shoppers trust (100+ reviews or a 100+ 'bought in past month' badge), or
      - it is on Temu or Shein (they advertise hard and deliver in about a week).
    Everything else is a HIDDEN or WEAK copy: found only by photo, few reviews, a far-away marketplace, or about the brand's price."""
    host = (urlparse(h.get("link") or "").netloc or "").lower().replace("www.", "")
    pr = price_to_number(h.get("price_text"))
    cheaper = (pr is None) or (not local_brand_price) or (pr < WEAK_PRICE_SHARE * local_brand_price)
    if any(w in host for w in FAR_AWAY):
        return "weak", "slow delivery from overseas"
    if any(w in host for w in FAST_CHEAP):
        return "strong", "on Temu or Shein"
    trusted = _num(h.get("reviews")) >= CREDIBLE_REVIEWS or _bought(h.get("bought")) >= 100
    if h.get("found_by_words"):
        spot = "%s result %d for the product words" % (h.get("where") or "search", h.get("rank") or 0)
        if cheaper:
            return "strong", spot
        if trusted:                      # same price, but it is right there in the results with reviews and sales behind it
            return "strong", spot + ", with %s reviews%s" % ("{:,}".format(_num(h.get("reviews"))), (" and " + h["bought"]) if h.get("bought") else "")
        return "weak", "about the brand's price, few reviews"
    if trusted and cheaper:
        return "strong", "a trusted Amazon listing (%s reviews%s)" % ("{:,}".format(_num(h.get("reviews"))), (", " + h["bought"]) if h.get("bought") else "")
    if h.get("looked_up"):
        return "weak", "not in the top results, %s reviews" % "{:,}".format(_num(h.get("reviews")))
    return "weak", "found only by photo"


def money_ok(price_text, cc):
    """A listing priced in another country's money is that country's listing, not this one's."""
    t = (price_text or "").strip()
    if not t:
        return True
    if cc == "au":
        return t.startswith("A$") or t.startswith("AU$")
    if cc == "nz":
        return t.startswith("NZ$")
    if cc == "ca":
        return t.startswith("CA$") or t.startswith("C$")
    if cc == "uk":
        return t.startswith("£")
    if cc == "de":
        return "€" in t
    if cc == "us":
        return t.startswith("$") or t.startswith("US$")
    return True


def counts_here(c, cc):
    """Does this listing really belong in this country's list?
    - a shop with another country's web address (.com.au in the US results) does not
    - a price in another country's money does not
    - with no price shown: only a local shop, that country's Amazon/Walmart, or a marketplace that ships worldwide"""
    host = (urlparse(c.get("link") or "").netloc or "").lower().replace("www.", "")
    home = shop_country(c.get("link"))
    if cc == "nz" and host == "amazon.com.au":
        return True                      # New Zealand has no Amazon of its own; Amazon Australia serves it
    if home and home != cc:
        return False
    ptxt = (c["seen_in"].get(cc) or {}).get("price_text")
    if ptxt:
        return money_ok(ptxt, cc)
    if home == cc or any(w in host for w in WORLDWIDE):
        return True
    return HOME_OF.get(host) == cc


def collect(a):
    key, src = get_serpapi_key()
    if not key:
        print("NO-EXTRAS MODE: " + src + ". Picture search skipped; the map falls back to the category check.")
        return
    os.makedirs(a.out, exist_ok=True)
    cands, per_cc = {}, {}
    for cc in [c.strip().lower() for c in a.countries.split(",") if c.strip()]:
        raw = os.path.join(a.out, "%s_%s_lens.json" % (a.slug, cc))
        if os.path.exists(raw):
            d = json.load(open(raw))
        else:
            q = urllib.parse.urlencode({"engine": "google_lens", "url": a.image_url, "country": LENS_CC.get(cc, cc), "hl": "en", "api_key": key})
            d = None
            for attempt in range(3):
                try:
                    d = fetch_json("https://serpapi.com/search.json?" + q, timeout=120)
                    break
                except Exception as e:
                    d = {"error": str(e)[:160]}
                    time.sleep(5 * (attempt + 1))
            if not d.get("error"):
                json.dump(d, open(raw, "w"))
        vm = d.get("visual_matches") or []
        rows = []
        for m in vm:
            pr = m.get("price")
            ptxt = pr.get("value") if isinstance(pr, dict) else pr
            k = kind(m.get("source"), m.get("link"), cc, a.brand_domain)
            if not ptxt and k in ("not a shop",):
                continue
            ck = (urlparse(m.get("link") or "").netloc.replace("www.", ""), (m.get("title") or "")[:60])
            c = cands.setdefault(ck, {"source": m.get("source"), "title": m.get("title"), "link": m.get("link"), "thumbnail": m.get("thumbnail"),
                                      "price_text": ptxt, "seen_in": {}, "priced": bool(ptxt)})
            c["seen_in"][cc] = {"kind": k, "price_text": ptxt}
            rows.append(ck)
        per_cc[cc] = len(vm)
        print("%-3s %3d picture matches, %2d real listings%s" % (cc, len(vm), len(rows), (" | ERROR " + d["error"]) if d.get("error") else ""))
        sys.stdout.flush()
    # Priced listings first, then unpriced listings from real shops, then the rest; the brand itself last.
    # NEVER cut a priced listing or a listing from a chain or marketplace: big US shops (Walmart, Amazon.com) often show
    # no price in a picture search, and dropping them once made a country look green when the same object was on sale there.
    def is_shop(c):
        host = (urlparse(c.get("link") or "").netloc or "").lower()
        return (any(v["kind"] in ("big chain", "marketplace") for v in c["seen_in"].values())
                or any(w in host for w in WORLDWIDE + FAR_AWAY) or host.replace("www.", "") in HOME_OF)
    order = sorted(cands.values(), key=lambda c: (not c["priced"], not is_shop(c), all(v["kind"] == "the brand" for v in c["seen_in"].values()), -len(c["seen_in"])))
    must = [c for c in order if c["priced"] or is_shop(c)]
    rest = [c for c in order if not (c["priced"] or is_shop(c))]
    order = must + rest[: max(0, a.max - len(must))]
    for i, c in enumerate(order):
        c["n"] = i
        tp = os.path.join(a.out, "%s_thumb_%02d.jpg" % (a.slug, i))
        if c.get("thumbnail") and not os.path.exists(tp):
            try:
                req = urllib.request.Request(c["thumbnail"], headers={"User-Agent": UA})
                open(tp, "wb").write(urllib.request.urlopen(req, timeout=40).read())
            except Exception:
                pass
        c["thumb_file"] = tp if os.path.exists(tp) else None
    json.dump({"slug": a.slug, "image_url": a.image_url, "brand_domain": a.brand_domain, "matches_per_country": per_cc, "candidates": order},
              open(os.path.join(a.out, "%s_candidates.json" % a.slug), "w"), indent=1, ensure_ascii=False)
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
                dr.text((x + 4, y + 2), "#%d %s" % (c["n"], (c["source"] or "")[:20]), fill="black", font=f)
                dr.text((x + 4, y + 21), "%s  [%s]" % (c.get("price_text") or "no price", ",".join(sorted(c["seen_in"]))[:17]), fill=(160, 0, 0), font=f)
            # the first page keeps the plain name (the report prints it); later pages are _sheet_2.jpg, _sheet_3.jpg ...
            sp = os.path.join(a.out, "%s_sheet%s.jpg" % (a.slug, "" if pi == 0 else "_%d" % (pi + 1)))
            sheet.save(sp, quality=82)
            print("contact sheet %d of %d: %s" % (pi + 1, len(pages), sp))
        if len(pages) > 1:
            print("LOOK AT EVERY SHEET. Listings with 'no price' count too: big shops like Walmart and Amazon.com often show no price in a picture search.")
    except Exception as e:
        print("no contact sheet (%s) — open the thumbnails one by one" % str(e)[:60])
    print("candidates:", len(order), "| now LOOK at the sheet and run: decide --same <numbers>")


def decide(a):
    data = json.load(open(os.path.join(a.out, "%s_candidates.json" % a.slug)))
    same = set(int(x) for x in a.same.split(",") if x.strip() != "")
    out = []
    searched = [c for c in data.get("matches_per_country", {})]
    asked = [c.strip().lower() for c in a.countries.split(",") if c.strip()]
    skipped = [c for c in asked if c not in searched]
    if skipped:
        print("not coloured (never searched, run collect for them first):", ", ".join(skipped))
    run_dir = os.path.dirname(os.path.abspath(a.out))
    vis_file = os.path.join(run_dir, "visible", "%s_visible.json" % a.slug)
    visible = json.load(open(vis_file)).get("countries", {}) if os.path.exists(vis_file) else None
    lk_file = os.path.join(run_dir, "visible", "%s_lookups.json" % a.slug)
    looked = json.load(open(lk_file)) if os.path.exists(lk_file) else {}
    if visible is None:
        print("NOTE: visibility_check.py has not run for this product, so every copy counts as if shoppers can find it. Run it next; it costs nothing.")
    for cc in [c for c in asked if c in searched]:
        hits = []
        suppliers_here = 0
        for c in data["candidates"]:
            if c["n"] in same and cc in c["seen_in"] and c["seen_in"][cc]["kind"] != "the brand" and counts_here(c, cc):
                k = c["seen_in"][cc]["kind"]
                if k == "not a shop":
                    continue
                if any(w in (urlparse(c.get("link") or "").netloc or "").lower() for w in SUPPLIER_SITES):
                    suppliers_here += 1          # AliExpress, Alibaba and the like are where YOU buy it, not who you compete with
                    continue
                hits.append({"source": tidy_source(c["source"], c["link"]), "title": (c["title"] or "")[:90], "link": c["link"], "price_text": c["seen_in"][cc]["price_text"],
                             "kind": k, "thumb_file": c.get("thumb_file")})
        for h in hits:
            h["price_text"] = (h.get("price_text") or "").replace("*", "") or None
        local_bp = brand_price_in(cc, a.brand_price, a.brand_currency)
        # what the single-listing lookups told us: real price, reviews, sales badge
        for h in hits:
            host = (urlparse(h.get("link") or "").netloc or "").lower().replace("www.", "")
            m = re.search(r"/dp/([A-Z0-9]{10})", h.get("link") or "")
            lk = looked.get(host + "/" + m.group(1)) if m else None
            if lk:
                h["looked_up"] = True
                h["reviews"], h["bought"] = lk.get("reviews"), lk.get("bought")
                if not h.get("price_text") and lk.get("price_text") and money_ok(lk["price_text"], cc):
                    h["price_text"] = lk["price_text"]
        # the same object in the top word-search results (what a shopper actually sees)
        for v in (visible or {}).get(cc, []):
            if v.get("price_text") and not money_ok(v["price_text"], cc) and not (cc == "nz" and v.get("where") == "Amazon"):
                continue                 # (New Zealand is served by Amazon Australia, so its A$ prices do count there)
            hits.append({"source": v.get("source"), "title": v.get("title"), "link": v.get("link"), "price_text": v.get("price_text"),
                         "kind": "big chain" if v.get("big_chain") else "marketplace", "thumb_file": v.get("thumb_file"), "found_by_words": True,
                         "where": v.get("where"), "rank": v.get("rank"), "reviews": v.get("reviews"), "bought": v.get("bought")})
        chain = [h for h in hits if h["kind"] == "big chain" and h.get("price_text")]      # a chain must show a price to count as "on the shelf"
        if chain:
            status, why = "blocked", "The same object is sold by %s%s" % (chain[0]["source"], (" at " + chain[0]["price_text"]) if chain[0].get("price_text") else "")
        elif hits:
            for h in hits:
                h["strength"], h["strength_why"] = (findable_strength(h, local_bp) if visible is not None else copy_strength(h, local_bp))
            strong = [h for h in hits if h["strength"] == "strong"]
            if strong:
                top = sorted(strong, key=lambda h: (not h.get("found_by_words"), h.get("rank") or 99, price_to_number(h.get("price_text")) or 9e9))[0]
                if visible is not None:
                    status, why = "crowded", "%s%s: %s" % (top["source"], (" at " + top["price_text"]) if top.get("price_text") else "", top["strength_why"])
                else:
                    status, why = "crowded", "The same object is on %s%s" % (top["source"], (" at " + top["price_text"]) if top.get("price_text") else "")
                if len(hits) > 1:
                    why += ". %d other cop%s" % (len(hits) - 1, "y" if len(hits) == 2 else "ies")
            elif visible is not None:
                best = sorted(hits, key=lambda h: (price_to_number(h.get("price_text")) is None, price_to_number(h.get("price_text")) or 9e9))[0]
                status = "weak"
                why = "%d cop%s, all hard to find. Cheapest: %s%s (%s)" % (
                    len(hits), "y" if len(hits) == 1 else "ies", best["source"], (" at " + best["price_text"]) if best.get("price_text") else "", best["strength_why"])
            else:
                far = [h for h in hits if h["strength_why"].startswith("far-away")]
                near = [h for h in hits if not h["strength_why"].startswith("far-away")]
                bits = []
                if far:
                    bits.append("%s (slow delivery)" % far[0]["source"])
                if near:
                    bits.append("%s at %s, about the brand's price" % (near[0]["source"], near[0]["price_text"]))
                status, why = "weak", "Only weak copies: " + " and ".join(bits)
        else:
            status, why = "open", "Picture search found nobody but the brand selling this object here"
            if suppliers_here:
                why = "No shop sells this object here. It is only on supplier sites such as AliExpress, which is where you would buy it"
        # the price ladder: what the brand charges here against what the copies cost
        nums = sorted(x for x in (price_to_number(h.get("price_text")) for h in hits) if x)
        real = sorted(x for x in (price_to_number(h.get("price_text")) for h in hits if h.get("strength") == "strong" or h["kind"] == "big chain") if x)
        ladder = {"brand": round(local_bp, 2) if local_bp else None, "cheapest_copy": nums[0] if nums else None,
                  "typical_copy": nums[len(nums) // 2] if nums else None, "cheapest_real_copy": real[0] if real else None, "priced_copies": len(nums)}
        out.append({"cc": cc, "status": status, "why": why, "prices": ladder, "findability_checked": visible is not None,
                    "same_object_listings": hits, "picture_matches": data["matches_per_country"].get(cc)})
        print("%-3s %-8s %s" % (cc, status.upper(), why))
        if status in ("open", "weak"):
            unmarked = [c["n"] for c in data["candidates"] if c["n"] not in same and cc in c["seen_in"]
                        and c["seen_in"][cc]["kind"] in ("big chain", "marketplace") and counts_here(c, cc)]
            if unmarked:
                print("    CHECK BEFORE YOU TRUST THIS: %d chain or marketplace listings seen in %s were NOT marked as the same object: #%s."
                      % (len(unmarked), cc.upper(), ", #".join(str(n) for n in unmarked[:25])))
                print("    Open each one's picture (<slug>_thumb_NN.jpg) at full size. Green is only true if none of them is the same object.")
    json.dump({"slug": a.slug, "same": sorted(same), "brand_price": a.brand_price, "brand_currency": a.brand_currency, "countries": out},
              open(os.path.join(a.out, "%s_lens.json" % a.slug), "w"), indent=1, ensure_ascii=False)
    print("wrote:", os.path.join(a.out, "%s_lens.json" % a.slug))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["collect", "decide"])
    ap.add_argument("--slug", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--countries", default="au,us,uk,ca,de,nz")
    ap.add_argument("--image-url", default="")
    ap.add_argument("--brand-domain", default="")
    ap.add_argument("--brand-price", type=float, default=None, help="the brand's price as a plain number, e.g. 70")
    ap.add_argument("--brand-currency", default="usd", choices=sorted(PER_USD), help="the money that price is in: usd, aud, cad, gbp, eur or nzd")
    ap.add_argument("--same", default="")
    ap.add_argument("--max", type=int, default=48)
    a = ap.parse_args()
    collect(a) if a.mode == "collect" else decide(a)


if __name__ == "__main__":
    main()
