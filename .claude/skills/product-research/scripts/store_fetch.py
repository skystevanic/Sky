#!/usr/bin/env python3
"""Read a product page the tidy way.

Shopify stores publish their whole catalogue as data. This pulls:
  - the product: title, price, was-price, variants, description, images
  - the store: how many products, when the first one was created (launch date), newest additions
and downloads up to 3 product images for the picture comparison.

Usage: python3 store_fetch.py <product-url> --out <folder> [--images 3]
Writes <folder>/store.json and <folder>/img_1.jpg ...
Falls back to reading the page's own title / price / image if the store isn't Shopify.
"""
import argparse
import html as htmllib
import json
import os
import re
import sys
from urllib.parse import urlparse, urljoin

from common import fetch, fetch_json, UA


def strip_html(s, n=3000):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmllib.unescape(re.sub(r"\s+", " ", s)).strip()
    return s[:n]


def save_images(urls, out, n):
    saved = []
    for i, u in enumerate(urls[:n], 1):
        try:
            if u.startswith("//"):
                u = "https:" + u
            data = fetch(u, timeout=60, binary=True)
            ext = ".png" if ".png" in u.lower() else ".jpg"
            p = os.path.join(out, "img_%d%s" % (i, ext))
            open(p, "wb").write(data)
            # Stores often serve 5 MB pictures, PNGs or animated GIFs. Save every photo as a plain JPG no wider than 1600 px,
            # always named img_N.jpg, so it is quick to look at and the report can use it.
            try:
                from PIL import Image
                im = Image.open(p)
                im.seek(0)
                im = im.convert("RGB")
                if max(im.size) > 1600:
                    im.thumbnail((1600, 1600))
                jp = os.path.join(out, "img_%d.jpg" % i)
                im.save(jp, "JPEG", quality=85)
                if jp != p:
                    os.remove(p)
                p = jp
            except Exception:
                pass
            saved.append({"file": p, "src": u})
        except Exception as e:
            saved.append({"file": None, "src": u, "error": str(e)[:80]})
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--images", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    u = urlparse(a.url)
    root = "%s://%s" % (u.scheme or "https", u.netloc)
    m = re.search(r"/products/([^/?#]+)", u.path)
    handle = m.group(1) if m else None
    result = {"input_url": a.url, "store_root": root, "platform": "unknown"}

    # Supplier / marketplace links (AliExpress, Temu, Amazon, 1688) block readers. Say so, and say exactly what to paste.
    host = (u.netloc or "").lower()
    if any(k in host for k in ("aliexpress.", "temu.", "amazon.", "1688.", "alibaba.", "ebay.", "dhgate.")):
        site = next(k.rstrip(".") for k in ("aliexpress.", "temu.", "amazon.", "1688.", "alibaba.", "ebay.", "dhgate.") if k in host)
        slug = re.search(r"/item/([A-Za-z0-9-]{12,})/\d+\.html", u.path)  # old-style AliExpress links carry the title
        result.update({"platform": site + " (supplier/marketplace — blocks readers)", "input_kind": "supplier",
                       "title": slug.group(1).replace("-", " ") if slug else None,
                       "paste_needed": ["the product title as shown on the page", "the price shown (and the currency)",
                                        "the 'sold' or orders number if shown", "the shipping weight or size if shown",
                                        "drop the main product photo into the chat (or paste its image address)"]})
        json.dump(result, open(os.path.join(a.out, "store.json"), "w"), indent=2, ensure_ascii=False)
        print("platform:", result["platform"])
        print("PASTE NEEDED — this site blocks automatic reading. Ask the member for, in one message:")
        for i, x in enumerate(result["paste_needed"], 1):
            print("  %d. %s" % (i, x))
        if result.get("title"):
            print("title guessed from the link:", result["title"])
        print("Then continue: the title becomes the search words, the price becomes the landed-cost estimate, and the photo is used for the picture check.")
        print("wrote:", os.path.join(a.out, "store.json"))
        return

    # 1) Shopify product feed
    if handle:
        try:
            p = fetch_json("%s/products/%s.json" % (root, handle))["product"]
            variants = [{"title": v.get("title"), "price": v.get("price"), "was": v.get("compare_at_price"),
                         "available": v.get("available")} for v in p.get("variants", [])]
            result.update({
                "platform": "shopify",
                "title": p.get("title"), "vendor": p.get("vendor"), "product_type": p.get("product_type"),
                "created_at": p.get("created_at"), "updated_at": p.get("updated_at"),
                "price_min": min((float(v["price"]) for v in variants if v.get("price")), default=None),
                "price_max": max((float(v["price"]) for v in variants if v.get("price")), default=None),
                "was_price": next((v["was"] for v in variants if v.get("was")), None),
                "n_variants": len(variants), "variants": variants[:40],
                "description": strip_html(p.get("body_html")),
                "images": [im.get("src") for im in p.get("images", [])],
                "tags": p.get("tags"),
            })
        except Exception as e:
            result["product_feed_error"] = str(e)[:120]

    # 2) Shopify store feed (catalogue size + launch date)
    try:
        ps = fetch_json("%s/products.json?limit=250" % root).get("products", [])
        if ps:
            result["platform"] = "shopify"
            ps_sorted = sorted(ps, key=lambda x: x.get("created_at") or "")
            result["store"] = {
                "n_products": len(ps), "first_product_created": ps_sorted[0].get("created_at"),
                "newest": [{"title": x.get("title"), "created_at": (x.get("created_at") or "")[:10],
                            "price": (x.get("variants") or [{}])[0].get("price")} for x in ps_sorted[-8:][::-1]],
                "note": "250 is the feed's page limit; a store with 250 has at least that many.",
            }
    except Exception as e:
        result["store_feed_error"] = str(e)[:120]

    # which money is the price in? (Shopify says so on the product page)
    try:
        pg = fetch(a.url, timeout=40)
        mcur = re.search(r'"currency"\s*:\s*"([A-Z]{3})"', pg) or re.search(r'Shopify\.currency\s*=\s*\{"active":"([A-Z]{3})"', pg) or re.search(r'property="og:price:currency"\s+content="([A-Z]{3})"', pg)
        if mcur:
            result["price_currency"] = mcur.group(1)
    except Exception:
        pass

    # 3) Fallback: read the page itself
    if result.get("platform") != "shopify" or not result.get("title"):
        try:
            page = fetch(a.url, timeout=60)
            def meta(prop):
                mm = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']+)' % re.escape(prop), page, re.I)
                return htmllib.unescape(mm.group(1)) if mm else None
            result.setdefault("title", meta("og:title") or strip_html(re.search(r"<title>(.*?)</title>", page, re.S | re.I).group(1) if re.search(r"<title>", page, re.I) else "", 200))
            result.setdefault("price_min", None)
            pm = meta("product:price:amount") or meta("og:price:amount")
            if pm:
                result["price_min"] = float(re.sub(r"[^\d.]", "", pm) or 0) or None
            result["price_currency"] = meta("product:price:currency") or meta("og:price:currency")
            og = meta("og:image")
            if og:
                result.setdefault("images", [])
                result["images"].insert(0, urljoin(a.url, og))
            result["description"] = result.get("description") or meta("og:description") or meta("description")
            result["page_text_sample"] = strip_html(page, 1500)
            if result.get("platform") != "shopify":
                result["platform"] = "not-shopify (feed unavailable; page read only)"
        except Exception as e:
            result["page_error"] = str(e)[:160]
            result["platform"] = result.get("platform") if result.get("platform") != "unknown" else "unreadable (blocked or down)"

    result["saved_images"] = save_images(result.get("images") or [], a.out, a.images)
    json.dump(result, open(os.path.join(a.out, "store.json"), "w"), indent=2, ensure_ascii=False)

    # plain summary
    print("platform:", result.get("platform"))
    print("title:", result.get("title"))
    print("price:", result.get("price_currency") or "(currency not shown — ask the member)", result.get("price_min"), "-", result.get("price_max"), "| was:", result.get("was_price"), "| variants:", result.get("n_variants"))
    print("product created:", (result.get("created_at") or "?")[:10])
    st = result.get("store")
    if st:
        print("store: %s products, first created %s" % (st["n_products"], (st["first_product_created"] or "?")[:10]))
        for x in st["newest"][:5]:
            print("   newest:", x["created_at"], x["title"][:60], x["price"])
    print("images saved:", sum(1 for s in result["saved_images"] if s.get("file")), "— LOOK at them and pick the cleanest product-only photo for the picture search")
    for k in ("product_feed_error", "store_feed_error", "page_error"):
        if result.get(k):
            print(k + ":", result[k])
    print("wrote:", os.path.join(a.out, "store.json"))


if __name__ == "__main__":
    main()
