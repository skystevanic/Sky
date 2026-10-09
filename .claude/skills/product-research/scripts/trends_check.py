#!/usr/bin/env python3
"""Demand check — is interest in this product rising, flat or falling? Google Trends over the last 2 YEARS via SerpApi (1 search per place). Two years on purpose: five flatters old fads.

Google Trends gives a 0–100 interest line, not a count of searches. So this answers DIRECTION and SEASON, not size:
  - growth: the last 12 months against the 12 months before
  - season: which months peak, and whether we're heading into the peak or out of it
  - level: where interest sits today against its 2-year high
Size comes from the Amazon step ("bought in past month") — quote the two together.

Usage: python3 trends_check.py --slug loom --keyword "darning loom" --places world,us,au --out <run>/trends
Writes <out>/<slug>_<place>_trends.json (raw, cached) and <out>/<slug>_trends.json (summary with a small line for the report).
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
from collections import defaultdict

from common import get_serpapi_key, fetch_json

GEO = {"world": "", "us": "US", "au": "AU", "uk": "GB", "ca": "CA", "de": "DE", "nz": "NZ"}
LABEL = {"world": "Worldwide", "us": "United States", "au": "Australia", "uk": "United Kingdom", "ca": "Canada", "de": "Germany", "nz": "New Zealand"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def summarise(place, d):
    pts = []
    for t in ((d.get("interest_over_time") or {}).get("timeline_data") or []):
        v = (t.get("values") or [{}])[0].get("extracted_value")
        ts = t.get("timestamp")
        if v is not None and ts:
            pts.append((int(ts), int(v)))
    cutoff = max(t for t, _ in pts) - 730 * 86400 if pts else 0
    pts = [(t, v) for t, v in pts if t >= cutoff]          # last 2 years only (older saved files get trimmed too)
    if len(pts) < 20:
        return {"place": place, "label": LABEL[place], "direction": "no data", "why": "Google Trends has too little data for this phrase here."}
    vals = [v for _, v in pts]
    n = len(vals)
    per_year = n // 2
    last, prev = vals[-per_year:], vals[-2 * per_year:-per_year]
    a, b = sum(last) / len(last), sum(prev) / max(1, len(prev))
    # Niche phrases are full of zeros (Google shows 0 below its threshold), which makes averages and percentages balloon.
    # So: call thin data thin, compare MIDDLE values not averages, and flag one-off spikes.
    zero_share = sum(1 for v in vals if v == 0) / float(n)
    med = lambda xs: sorted(xs)[len(xs) // 2]
    ma, mb = med(last), med(prev)
    growth = round((ma - mb) / mb * 100) if mb > 0 else None
    spike = max(last) >= 4 * max(1, ma)
    if zero_share > 0.35:
        return {"place": place, "label": LABEL[place], "direction": "thin", "growth_pct": None, "zero_share": round(zero_share, 2),
                "why": "Too few searches here for Google to measure reliably (%d%% of weeks read zero). Use Amazon units and ad velocity instead." % round(zero_share * 100),
                "line": [round(sum(vals[i:i + max(1, n // 52)]) / len(vals[i:i + max(1, n // 52)])) for i in range(0, n, max(1, n // 52))]}
    by_month = defaultdict(list)
    for ts, v in pts:
        by_month[time.gmtime(ts).tm_mon].append(v)
    month_avg = {m: sum(x) / len(x) for m, x in by_month.items()}
    overall = sum(month_avg.values()) / 12
    peak = sorted(month_avg, key=month_avg.get, reverse=True)[:3]
    seasonal = (max(month_avg.values()) / overall) >= 1.6 if overall > 0 else False
    if growth is None or a < 3:
        direction = "tiny"
    elif growth >= 25:
        direction = "rising"
    elif growth <= -20:
        direction = "falling"
    else:
        direction = "steady"
    now_m = time.gmtime().tm_mon
    to_peak = min(((p - now_m) % 12) for p in peak)
    gtxt = "more than 4x" if (growth or 0) > 300 else ("%s%s%%" % ("+" if (growth or 0) >= 0 else "", growth))
    why = "A typical week in the last 12 months is %s the year before" % (gtxt if "x" in gtxt else gtxt + " on")
    if spike:
        hi = max(range(len(last)), key=lambda i: last[i]); hts = pts[-per_year:][hi][0]
        why += "; includes a spike around %s — check it isn't a one-off" % time.strftime("%b %Y", time.gmtime(hts))
    if seasonal:
        why += "; seasonal, busiest months %s" % ", ".join(MONTHS[m - 1] for m in sorted(peak))
    step = max(1, n // 52)
    line = [round(sum(vals[i:i + step]) / len(vals[i:i + step])) for i in range(0, n, step)]
    return {"place": place, "label": LABEL[place], "direction": direction, "growth_pct": growth, "seasonal": seasonal,
            "peak_months": [MONTHS[m - 1] for m in sorted(peak)], "months_to_peak": to_peak if seasonal else None,
            "now_vs_high": round(vals[-1] / max(vals) * 100) if max(vals) else None, "avg_last_year": round(a, 1), "spike": spike, "zero_share": round(zero_share, 2), "why": why, "line": line}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--places", default="world")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    key, src = get_serpapi_key()
    if not key:
        print("NO-EXTRAS MODE: " + src + ". Demand check skipped; treat demand direction as an Assumption.")
        return
    out = []
    for place in [p.strip().lower() for p in a.places.split(",") if p.strip()]:
        if place not in GEO:
            continue
        raw = os.path.join(a.out, "%s_%s_trends.json" % (a.slug, place))
        if os.path.exists(raw):
            d = json.load(open(raw))
        else:
            today = time.strftime("%Y-%m-%d"); two_back = "%d%s" % (int(today[:4]) - 2, today[4:])
            q = {"engine": "google_trends", "q": a.keyword, "data_type": "TIMESERIES", "date": "%s %s" % (two_back, today), "api_key": key}
            if GEO[place]:
                q["geo"] = GEO[place]
            d = None
            for attempt in range(3):
                try:
                    d = fetch_json("https://serpapi.com/search.json?" + urllib.parse.urlencode(q), timeout=120)
                    break
                except Exception as e:
                    d = {"error": str(e)[:160]}
                    time.sleep(5 * (attempt + 1))
            if d.get("error"):
                print("%-6s ERROR %s" % (place, d["error"]))
                out.append({"place": place, "label": LABEL[place], "direction": "no data", "why": d["error"]})
                continue
            json.dump(d, open(raw, "w"))
        s = summarise(place, d)
        out.append(s)
        print("%-6s %-8s %s" % (place, s["direction"].upper(), s["why"]))
        sys.stdout.flush()
    json.dump({"slug": a.slug, "keyword": a.keyword, "places": out}, open(os.path.join(a.out, "%s_trends.json" % a.slug), "w"), indent=2)
    print("wrote:", os.path.join(a.out, "%s_trends.json" % a.slug))


if __name__ == "__main__":
    main()
