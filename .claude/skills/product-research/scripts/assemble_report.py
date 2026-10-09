#!/usr/bin/env python3
"""Put the report together. You write ONLY your judgement; this copies everything else from the files the other scripts made.

Usage: python3 assemble_report.py <run folder>
Reads  <run>/judgement.json   (you write this — see reference/report-fields.md and examples/sample-run/judgement.json)
Reads  <run>/grid, amazon, trends, lens, meta, asis and <run>/<slug>/ (made by the other scripts)
Writes <run>/report.json      (then: python3 build_report.py <run>/report.json --full)

Everything in report.json uses paths RELATIVE to the run folder, so the folder can be moved or zipped.
"""
import glob
import json
import os
import sys

CUR = {"au": "A$", "us": "US$", "uk": "£", "ca": "C$", "de": "€", "nz": "NZ$"}
ACUR = dict(CUR, nz="A$")
NAMES = {"au": "Australia", "us": "the US", "uk": "the UK", "ca": "Canada", "de": "Germany", "nz": "New Zealand"}


def money(cc, v, table=CUR):
    return ("%s%.0f" % (table.get(cc, ""), v)) if isinstance(v, (int, float)) and v else (v or "")


def load(path):
    return json.load(open(path)) if os.path.exists(path) else None


def rel(run, path):
    if not path:
        return None
    return os.path.relpath(path, run) if os.path.isabs(path) else path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    run = os.path.abspath(sys.argv[1])
    J = load(os.path.join(run, "judgement.json"))
    if not J:
        print("No judgement.json in", run, "— copy examples/sample-run/judgement.json and fill it in.")
        sys.exit(1)
    products, problems = [], []
    for j in J["products"]:
        s = j["slug"]
        p = {k: j.get(k) for k in ("slug", "name", "one_liner", "url", "brand", "category", "price", "ad_days", "store_platform", "store_launched",
                                   "store_products", "snapshot", "gates", "scores", "overall", "confidence", "best_region", "angles", "tile_notes")}
        p["final"] = {"verdict": j.get("verdict"), "why": j.get("why") or [], "risk": j.get("risk"), "fastest_test": j.get("next") or []}
        for need in ("name", "one_liner", "verdict", "overall", "scores", "why"):
            if not j.get(need):
                problems.append("%s: '%s' is missing in judgement.json" % (s, need))
        g = load(os.path.join(run, "grid", "%s_grid.json" % s))
        if g:
            p["regions"] = [{"cc": c["cc"], "status": c.get("status"), "why": (j.get("category_notes") or {}).get(c["cc"]) or c.get("why"), "sellers": c.get("distinct_sellers"),
                             "cheapest": money(c["cc"], c.get("cheapest")), "typical": money(c["cc"], c.get("typical")),
                             "top": "%s (%s)" % ((c.get("most_reviewed") or {}).get("seller"), (c.get("most_reviewed") or {}).get("reviews"))} for c in g.get("countries", []) if c.get("status") != "error"]
        a = load(os.path.join(run, "amazon", "%s_amazon.json" % s))
        if a:
            p["amazon"] = []
            for c in a.get("countries", []):
                c = dict(c)
                c["cheapest"], c["typical"] = money(c["cc"], c.get("cheapest"), ACUR), money(c["cc"], c.get("typical"), ACUR)
                p["amazon"].append(c)
        t = load(os.path.join(run, "trends", "%s_trends.json" % s))
        if t:
            p["trends"] = t.get("places")
        ln = load(os.path.join(run, "lens", "%s_lens.json" % s))
        if ln:
            for c in ln["countries"]:
                for h in c.get("same_object_listings") or []:
                    h["thumb_file"] = rel(run, h.get("thumb_file"))
            p["lens"] = ln["countries"]
            sheet = os.path.join(run, "lens", "%s_sheet.jpg" % s)
            p["lens_sheet"] = rel(run, sheet) if os.path.exists(sheet) else None
        else:
            problems.append("%s: no picture-search result (lens/%s_lens.json). Run lens_check.py collect, LOOK at the sheet, then decide." % (s, s))
        sup = load(os.path.join(run, "supplier", "%s_supplier.json" % s))
        if sup:
            for l in sup.get("listings") or []:
                if l.get("thumb_file"):
                    l["thumb_file"] = rel(run, l["thumb_file"])
            p["supplier"] = sup
        m = load(os.path.join(run, "meta", "%s_meta.json" % s))
        if m:
            m["takeaway"] = j.get("advertiser_takeaway") or m.get("plain")
            p["meta"] = m
        else:
            problems.append("%s: no advertiser result (meta/%s_meta.json). Run meta_ads_apify.py." % (s, s))
        asis = load(os.path.join(run, "asis", "%s_asis.json" % s))
        if asis:
            am = {x["cc"]: x for x in (p.get("amazon") or [])}
            rows = []
            for c in asis.get("countries", []):
                c = dict(c)
                c["image"] = rel(run, c.get("image"))
                note = (j.get("country_takeaways") or {}).get(c["cc"])
                if not note:
                    bits = []
                    if c.get("top5"):
                        bits.append("First result in %s: %s (%s)." % (NAMES.get(c["cc"], c["cc"]), c["top5"][0]["domain"], c["top5"][0]["kind"]))
                    strip = sorted({x.get("source") for x in c.get("popular_products") or [] if x.get("source")})[:5]
                    if strip:
                        bits.append("In the product strip: %s." % ", ".join(strip))
                    if am.get(c["cc"], {}).get("pressure") in ("high", "medium", "low"):
                        bits.append("Amazon here is %s." % {"high": "crowded", "medium": "busy", "low": "quiet"}[am[c["cc"]]["pressure"]])
                    note = " ".join(bits)
                c["takeaway"] = note
                rows.append(c)
            p["asis"] = rows
        # pictures for the side-by-side
        cmpj = dict(j.get("compare") or {})
        imgs = sorted(glob.glob(os.path.join(run, s, "img_*")))
        pick = cmpj.pop("brand_photo", None)
        brand_img = os.path.join(run, s, pick) if pick else (imgs[0] if imgs else None)
        cmpj["brand_image"] = rel(run, brand_img)
        n = cmpj.pop("match_number", None)
        if n is not None:
            cmpj["match_image"] = "lens/%s_thumb_%02d.jpg" % (s, int(n))
        p["compare"] = cmpj
        products.append(p)
    products.sort(key=lambda x: -(x.get("overall") or 0))
    run_info = dict(J.get("run") or {})
    run_info.setdefault("title", "Product Research")
    run_info.setdefault("mode", "full")
    rep = {"run": run_info, "headline": J.get("headline") or (products[0].get("one_liner") if products else ""),
           "products": products, "ranking": [p["slug"] for p in products]}
    json.dump(rep, open(os.path.join(run, "report.json"), "w"), indent=1, ensure_ascii=False)
    print("wrote:", os.path.join(run, "report.json"))
    for x in problems:
        print("CHECK:", x)
    if not problems:
        print("All parts found. Next: python3 build_report.py '%s' --full" % os.path.join(run, "report.json"))


if __name__ == "__main__":
    main()
