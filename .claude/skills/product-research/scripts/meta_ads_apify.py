#!/usr/bin/env python3
"""How crowded is the ADVERTISING for this product right now? Facebook's Ad Library, read through Apify.

Why Apify: reading Facebook's pages from your own computer is against Meta's terms and could get your connection
blocked. Apify's servers do the reading instead. Your computer only talks to Apify.

Gives the three numbers that decide "get in" versus "you're late":
  - how many live ads use the product phrase
  - how many DIFFERENT brands are behind them (and whether one brand runs most of them)
  - when those ads started (one brand advertising for months = proof; dozens of brands in the last few weeks = a swarm)

SAFETY — this actor ignores its own result cap and will scroll (and bill) forever on a busy phrase. So this script never
waits for it to finish: it starts the run, watches the item count, and ABORTS the run at --cap ads or --max-seconds,
whichever comes first. Cost has been roughly US$6 per 1,000 ads. Check the cost line it prints.

Code lookup: Mac Keychain 'apify-api-token' → environment APIFY_TOKEN → ~/.product-research/config.json "apify_token".
No code → prints "skipped" and gives the link to open by hand instead.

Usage: python3 meta_ads_apify.py --slug loom --phrase "darning loom" --cap 250 --out <run>/meta
"""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

from common import CONFIG_FILE, UA

ACTOR = "apify~facebook-ads-scraper"
API = "https://api.apify.com/v2"


def get_token():
    if platform.system() == "Darwin":
        for label in ("apify-api-token",):
            try:
                out = subprocess.run(["security", "find-generic-password", "-s", label, "-w"], capture_output=True, text=True, timeout=10)
                if out.returncode == 0 and out.stdout.strip():
                    return out.stdout.strip(), "Mac Keychain"
            except Exception:
                pass
    t = os.environ.get("APIFY_TOKEN", "").strip()
    if t:
        return t, "environment setting APIFY_TOKEN"
    if os.path.exists(CONFIG_FILE):
        try:
            t = (json.load(open(CONFIG_FILE)).get("apify_token") or "").strip()
            if t:
                return t, CONFIG_FILE
        except Exception:
            pass
    return None, "no Apify code found"


def call(method, url, token, body=None, timeout=60):
    req = urllib.request.Request(url, method=method, data=(json.dumps(body).encode() if body is not None else None),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": UA})
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        return {"error": "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:200])}
    except Exception as e:
        return {"error": str(e)[:200]}


def library_url(phrase, country="ALL"):
    return ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=%s&search_type=keyword_exact_phrase&q=%s"
            % (country, urllib.parse.quote('"%s"' % phrase)))


def summarise(slug, phrase, items, cost, stopped_by, url, cap=250):
    adv = defaultdict(lambda: {"ads": 0, "oldest": None, "page_id": None, "likes": None, "domains": Counter(), "headline": None})
    months, domains, seen = Counter(), Counter(), set()
    for it in items:
        aid = it.get("adArchiveID") or it.get("adArchiveId") or it.get("ad_archive_id")
        if aid in seen:
            continue
        seen.add(aid)
        snap = it.get("snapshot") or {}
        page = it.get("pageName") or snap.get("page_name") or "?"
        link0 = snap.get("linkUrl") or snap.get("link_url") or ""
        host0 = (urlparse(link0).netloc or "").lower().replace("www.", "")
        shop0 = host0 if host0 and not any(x in host0 for x in ("facebook.", "instagram.", "fb.me", "fb.com", "wa.me", "linktr.ee", "amazon.", "temu.", "shopee.")) else None
        # Several Facebook pages often sell for ONE shop (creator and "journal" pages). Count the shop once.
        name = shop0 or page
        a = adv[name]
        a["ads"] += 1
        a.setdefault("pages", Counter())[page] += 1
        a["page_id"] = a["page_id"] or it.get("pageID") or it.get("pageId") or snap.get("page_id")
        sd = it.get("startDate") or it.get("start_date")
        if isinstance(sd, (int, float)) and sd > 0:
            d = datetime.fromtimestamp(sd, tz=timezone.utc)
            months[d.strftime("%Y-%m")] += 1
            if a["oldest"] is None or d.strftime("%Y-%m-%d") < a["oldest"]:
                a["oldest"] = d.strftime("%Y-%m-%d")
        a["likes"] = a["likes"] or snap.get("pageLikeCount") or (it.get("pageInfo") or {}).get("likes")
        a["headline"] = a["headline"] or (snap.get("title") or (snap.get("body") or {}).get("text") or "")[:90]
        link = snap.get("linkUrl") or snap.get("link_url") or ""
        host = (urlparse(link).netloc or "").lower().replace("www.", "")
        if host and "facebook." not in host and "instagram." not in host and host != "fb.me":
            domains[host] += 1
            a["domains"][host] += 1
            # the exact page the ad sends shoppers to, with tracking tails removed; the most used one becomes "their product page"
            a.setdefault("landing", Counter())[link.split("?")[0].split("#")[0]] += 1
    n_ads = len(seen)
    # Cut short = we stopped it, OR the reader itself stopped at the limit we gave it (it then says "finished on its own",
    # which once made a 250-of-1,200 sample look like the whole market). Either way every number is a minimum.
    capped = "stopped" in (stopped_by or "") or n_ads >= cap
    if capped and "stopped" not in (stopped_by or ""):
        stopped_by = "stopped at %d ads (there are more)" % n_ads
    # Brands replace their ads every few weeks, so counting ADS by start month always looks like a rush.
    # Count BRANDS by the month their oldest still-running ad began: that is the honest "who is new, who has lasted" picture.
    brand_months = Counter(v["oldest"][:7] for v in adv.values() if v.get("oldest"))
    top = sorted(adv.items(), key=lambda kv: -kv[1]["ads"])
    biggest_share = (top[0][1]["ads"] / float(n_ads)) if n_ads else 0
    today = datetime.now(timezone.utc)
    recent = sum(v for k, v in months.items() if (today.year * 12 + today.month) - (int(k[:4]) * 12 + int(k[5:])) <= 1)
    old = sum(v for k, v in months.items() if (today.year * 12 + today.month) - (int(k[:4]) * 12 + int(k[5:])) >= 6)
    n_adv = len(adv)
    real = [k for k, v in adv.items() if v["ads"] >= 3]
    # A fair swarm test counts BRANDS, not ads: ads turn over, so most live ads are recent for any product.
    def age_days(v):
        return (today.date() - datetime.strptime(v["oldest"], "%Y-%m-%d").date()).days if v["oldest"] else 0
    new_brands = sum(1 for v in adv.values() if age_days(v) < 60)
    proven_brands = sum(1 for v in adv.values() if age_days(v) >= 90)
    if n_ads == 0:
        pattern, plain = "nobody", "No live ads use this phrase."
    elif n_adv <= 3 or biggest_share >= 0.6:
        pattern = "one brand owns it" if old or biggest_share >= 0.6 else "hardly anyone"
        plain = "%d brands, but %s runs %d of the %d ads." % (n_adv, top[0][0], top[0][1]["ads"], n_ads)
    elif n_adv >= 10 and new_brands / float(n_adv) >= 0.7:
        pattern, plain = "a swarm, right now", "%d brands, and %d of them only started advertising it in the last two months." % (n_adv, new_brands)
    elif n_adv >= 10:
        pattern, plain = "crowded", "%d brands advertise it; %d have kept ads running 3+ months, %d are new in the last two months." % (n_adv, proven_brands, new_brands)
    else:
        pattern, plain = "a handful", "%d brands advertise it." % n_adv
    if capped:
        plain = "At least " + plain[0].lower() + plain[1:] + " We stopped counting at %d ads, so the real numbers are higher." % n_ads
    return {"slug": slug, "phrase": phrase, "checked": today.strftime("%Y-%m-%d"), "source": "Facebook Ad Library via Apify", "library_url": url,
            "ads_loaded": n_ads, "capped": capped, "stopped_by": stopped_by, "n_advertisers": n_adv, "advertisers_with_3_plus_ads": len(real),
            "biggest_advertiser_share": round(biggest_share, 2), "brands_new_in_last_2_months": new_brands, "brands_advertising_3_plus_months": proven_brands, "ads_started_last_2_months": recent, "ads_older_than_6_months": old,
            "pattern": pattern, "plain": plain, "months": dict(sorted(months.items())), "brand_months": dict(sorted(brand_months.items())),
            "top_advertisers": [{"name": (v["pages"].most_common(1)[0][0] if v.get("pages") else k), "pages": len(v.get("pages") or {}), "page_names": [n for n, _ in (v.get("pages") or Counter()).most_common(6)], "ads": v["ads"], "oldest_live_ad": v["oldest"], "page_likes": v["likes"], "headline": v["headline"], "shop": (v["domains"].most_common(1) or [[None]])[0][0], "product_page": ((v.get("landing") or Counter()).most_common(1) or [[None]])[0][0],
                                 "their_ads": ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&search_type=page&view_all_page_id=%s" % v["page_id"]) if v["page_id"] else None}
                                for k, v in top[:40]],
            "domains": dict(domains.most_common(25)), "cost_usd": cost}


def shop_ages(summary, out_dir, slug, top_n=12):
    """How old is each advertiser's SHOP? Facebook only shows ads that are still running, and brands replace their ads every
    few weeks, so 'oldest live ad' makes years-old brands look new. Most of these shops run on Shopify, whose public product
    list shows when each product was added. The oldest one is a floor for the shop's age ('open since at least ...'). Free."""
    from concurrent.futures import ThreadPoolExecutor
    cache_p = os.path.join(out_dir, "%s_shop_ages.json" % slug)
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}

    def one(shop):
        if shop in cache:
            return
        oldest = None
        try:
            for page in (1, 2):
                req = urllib.request.Request("https://%s/products.json?limit=250&page=%d" % (shop, page), headers={"User-Agent": UA, "Accept": "application/json"})
                prods = json.load(urllib.request.urlopen(req, timeout=12)).get("products") or []
                for pr in prods:
                    d = (pr.get("created_at") or pr.get("published_at") or "")[:10]
                    if d and (oldest is None or d < oldest):
                        oldest = d
                if len(prods) < 250:
                    break
        except Exception:
            pass
        cache[shop] = oldest
    shops = [t["shop"] for t in summary["top_advertisers"][:top_n] if t.get("shop")]
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, shops))
    json.dump(cache, open(cache_p, "w"), indent=1)
    today = datetime.now(timezone.utc).date()
    known = old = young = 0
    for t in summary["top_advertisers"]:
        d = cache.get(t.get("shop") or "")
        t["shop_open_since"] = d
        if d:
            days = (today - datetime.strptime(d, "%Y-%m-%d").date()).days
            known += 1
            old += days >= 365
            young += days < 120
    summary["shops_checked"], summary["shops_over_a_year_old"], summary["shops_under_4_months_old"] = known, old, young
    # A "swarm" of brand-new ads from shops that have existed for years is not a swarm. It is an established market.
    if known >= 4 and summary["pattern"] == "a swarm, right now" and old * 2 >= known:
        summary["pattern"] = "crowded"
        summary["plain"] = "%s%d brands. Their live ads are recent, but %d of the %d biggest shops we could date are more than a year old: an established market, not a new rush." % (
            "At least " if summary.get("capped") else "", summary["n_advertisers"], old, known)
    elif known >= 3:
        summary["plain"] += " Of the %d biggest shops we could date, %d are over a year old and %d opened in the last four months." % (known, old, young)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--phrase", required=True)
    ap.add_argument("--cap", type=int, default=250, help="stop the run once this many ads are in")
    ap.add_argument("--max-seconds", type=int, default=240)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    url = library_url(a.phrase)
    outp = os.path.join(a.out, "%s_meta.json" % a.slug)
    rawp = os.path.join(a.out, "%s_meta_raw.json" % a.slug)
    token, src = get_token()
    if not token:
        print("SKIPPED: " + src + ". Open this link yourself and note the '~N results' line and the brands on the first screen:\n" + url)
        return
    if os.path.exists(rawp):
        raw = json.load(open(rawp))
        items, cost, stopped = raw["items"], raw.get("cost_usd"), raw.get("stopped_by", "saved earlier")
    else:
        run = call("POST", "%s/acts/%s/runs" % (API, ACTOR), token, {"startUrls": [{"url": url}], "maxItems": a.cap, "resultsLimit": a.cap})
        if run.get("error"):
            print("could not start:", run["error"])
            return
        rid, ds = run["data"]["id"], run["data"]["defaultDatasetId"]
        t0, stopped, n = time.time(), "read every live ad", 0
        while True:
            time.sleep(7)
            st = call("GET", "%s/actor-runs/%s" % (API, rid), token).get("data") or {}
            n = ((call("GET", "%s/datasets/%s" % (API, ds), token).get("data")) or {}).get("itemCount", 0)
            status = st.get("status")
            print("  %3ds  %-10s %4d ads  US$%.2f" % (time.time() - t0, status, n, st.get("usageTotalUsd") or 0))
            sys.stdout.flush()
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break
            if n >= a.cap or time.time() - t0 > a.max_seconds:
                stopped = "stopped by us at %d ads" % n if n >= a.cap else "stopped by us after %ds" % a.max_seconds
                call("POST", "%s/actor-runs/%s/abort" % (API, rid), token)
                time.sleep(4)
                break
        if n >= a.cap and "stopped" not in stopped:
            stopped = "stopped at %d ads (there are more)" % a.cap
        time.sleep(6)                                   # the bill settles a few seconds after the run ends
        st = call("GET", "%s/actor-runs/%s" % (API, rid), token).get("data") or {}
        cost = round(st.get("usageTotalUsd") or 0, 2)
        req = urllib.request.Request("%s/datasets/%s/items?clean=1&limit=%d" % (API, ds, int(a.cap * 1.6) + 50), headers={"Authorization": "Bearer " + token, "User-Agent": UA})
        items = json.load(urllib.request.urlopen(req, timeout=120))
        json.dump({"items": items, "cost_usd": cost, "stopped_by": stopped, "run_id": rid}, open(rawp, "w"))
    s = summarise(a.slug, a.phrase, items, cost, stopped, url, cap=a.cap)
    s = shop_ages(s, a.out, a.slug)
    json.dump(s, open(outp, "w"), indent=1, ensure_ascii=False)
    print("%s | “%s”: %d ads, %d brands → %s. %s" % (a.slug, a.phrase, s["ads_loaded"], s["n_advertisers"], s["pattern"].upper(), s["plain"]))
    print("  months:", s["months"])
    for t in s["top_advertisers"][:8]:
        print("   %-30s %3d ads  oldest live ad %s  shop open since %s  likes %-8s %s" % (t["name"][:30], t["ads"], t["oldest_live_ad"], t.get("shop_open_since") or "?", t.get("page_likes"), t["shop"] or ""))
    print("  %s | cost US$%s" % (s["stopped_by"], ("%.2f" % cost) if cost is not None else "?"))
    print("wrote:", outp)


if __name__ == "__main__":
    main()
